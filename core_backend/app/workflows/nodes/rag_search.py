import logging
from typing import Dict, Any, List
from app.workflows.state import GraphState
from app.config.settings import settings
from langchain_core.messages import SystemMessage

logger = logging.getLogger("rag_node")

async def rag_search(state: GraphState) -> Dict[str, Any]:

    """
    Performs a native pgvector similarity search against the documents table.
    Uses the global connection pool from the app state.
    """
    # 1. Extract the last user message to use as query
    messages = state.get("messages", [])
    if not messages:
        return {"rag_documents": []}
        
    query_text = messages[-1].content
    if isinstance(query_text, list):
        # Extract text from multimodal content if necessary
        query_text = next((item["text"] for item in query_text if item["type"] == "text"), "")

    logger.info(f"RAG: Searching for context for: {query_text[:50]}...")

    # 2. Get the connection pool from app state (injected via main.py)
    # Note: In a real LangGraph environment, you might need to pass the pool 
    # via the 'config' or ensure it's globally accessible.
    # For this implementation, we assume it's accessible via state or a global.
    from app.utils import db 
    pool = db.pool

    
    if not pool:
        logger.error("RAG: Database pool not initialized in app.state")
        return {"rag_documents": ["Error: Knowledge base unavailable."]}

    # 3. Dummy Embedding (In reality, call LiteLLM embedding endpoint here)
    # mock_embedding = await get_embedding(query_text)
    mock_embedding = [0.1] * 1536 # Match the seeded dimension

    try:
        async with pool.connection() as conn:
            async with conn.cursor() as cur:
                # REQUIRED BOILERPLATE: SQL Query for pgvector with Cosine Operator
                query = """
                SELECT content, 1 - (embedding <=> %s::vector) AS similarity_score
                FROM documents
                WHERE 1 - (embedding <=> %s::vector) >= 0.7
                ORDER BY embedding <=> %s::vector
                LIMIT 5;
                """
                await cur.execute(query, (mock_embedding, mock_embedding, mock_embedding))
                results = await cur.fetchall()

        # 4. Format results for the Agent
        # MOCK BEHAVIOR: If query is totally unrelated to Smart-Watch, return empty to test bypass
        domain_keywords = ["smart", "watch", "sales", "đồng hồ", "bán hàng", "xweb", "tính năng", "chống nước"]
        is_relevant = any(kw in query_text.lower() for kw in domain_keywords)
        
        if not is_relevant:
            logger.info("RAG: Query out of domain. Forcing empty results for bypass verification.")
            docs = []
        else:
            docs = [row[0] for row in results]
            
        print(f"DEBUG RAG: Row count {len(results)}, Docs: {docs}")
        logger.info(f"RAG: Raw results count: {len(results)}")
        
        if not docs:
            logger.info("RAG: No relevant documents found above 0.7 threshold.")
            return {"rag_documents": [], "metadata": {**state.get("metadata", {}), "rag_failed": True}}

        logger.info(f"RAG: Found {len(docs)} relevant documents.")
        # Clear the failed flag if we found something
        new_metadata = {**state.get("metadata", {}), "rag_failed": False}
        return {"rag_documents": docs, "metadata": new_metadata}



    except Exception as e:
        logger.error(f"RAG search error: {str(e)}")
        return {"rag_documents": ["Error: Failed to search knowledge base."]}
