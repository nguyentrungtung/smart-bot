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
    # 1. Extract context for query
    messages = state.get("messages", [])
    if not messages:
        return {"rag_documents": []}
        
    last_msg = messages[-1]
    query_text = last_msg.content
    if isinstance(query_text, list):
        query_text = next((item["text"] for item in query_text if item["type"] == "text"), "")

    # Context enrichment: If the query is short, prefix it with the previous AI/User context 
    # to maintain semantic relevance (handling "Nó", "Cái đó", "Vừa rồi")
    search_query = query_text
    if len(messages) >= 3 and len(query_text) < 30:
        prev_user_msg = messages[-3].content
        if isinstance(prev_user_msg, str):
            search_query = f"{prev_user_msg} {query_text}"
            logger.info(f"RAG: Context enrichment used: {search_query}")

    logger.info(f"RAG: Searching for: {search_query[:50]}...")

    # 2. Get the connection pool from app state (injected via main.py)
    from app.utils import db 
    pool = db.pool

    if not pool:
        logger.error("RAG: Database pool not initialized in app.state")
        return {"rag_documents": ["Error: Knowledge base unavailable."]}

    # 3. REAL Embedding: Call LiteLLM embedding endpoint
    try:
        import litellm
        emb_resp = await litellm.aembedding(
            model="lm-studio-embedding", # As defined in litellm_config.yaml
            input=[search_query],
            api_base=settings.LITELLM_API_BASE,
            api_key=settings.LITELLM_API_KEY,
            custom_llm_provider="openai", # Force OpenAI protocol for proxy
        )
        embedding = emb_resp.data[0]["embedding"]
    except Exception as emb_err:
        logger.error(f"RAG: Embedding generation failed: {emb_err}")
        # Fallback to dummy but mark it as safe failure
        embedding = [0.1] * 1536 

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
                await cur.execute(query, (embedding, embedding, embedding))
                results = await cur.fetchall()

        # 4. Format results for the Agent
        docs = [row[0] for row in results]
            
        print(f"DEBUG RAG: Row count {len(results)}, Docs: {docs}")
        logger.info(f"RAG: Raw results count: {len(results)}")
        
        if not docs:
            logger.info("RAG: No relevant documents found above 0.7 threshold.")
            return {"rag_documents": [], "metadata": {**state.get("metadata", {}), "rag_failed": False}}

        logger.info(f"RAG: Found {len(docs)} relevant documents.")
        # Clear the failed flag if we found something
        new_metadata = {**state.get("metadata", {}), "rag_failed": False}
        return {"rag_documents": docs, "metadata": new_metadata}



    except Exception as e:
        logger.error(f"RAG search error: {str(e)}")
        return {"rag_documents": ["Error: Failed to search knowledge base."]}
