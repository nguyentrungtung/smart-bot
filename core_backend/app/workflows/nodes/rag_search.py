import logging
from typing import Dict, Any, List
from app.workflows.state import GraphState
from app.config.settings import settings

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
    if len(query_text) < 30 and len(messages) >= 2:
        # Build a context window from the last 2 turns (human + AI) before this message
        context_parts = []
        for m in messages[-3:-1]:  # up to 2 messages before current
            c = m.content
            if isinstance(c, str) and c.strip():
                context_parts.append(c.strip())
            elif isinstance(c, list):
                txt = " ".join(b.get("text", "") for b in c if isinstance(b, dict) and b.get("type") == "text")
                if txt.strip():
                    context_parts.append(txt.strip())
        if context_parts:
            search_query = " ".join(context_parts) + " " + query_text
            logger.info(f"RAG: Context enrichment used: {search_query[:80]}")

    from app.workflows.nodes.tool_defs import BYPASS_KEYWORDS
    is_whitelisted = any(kw in search_query.lower() for kw in BYPASS_KEYWORDS)
    if is_whitelisted:
        logger.info(f"RAG: Query '{search_query[:20]}' matches bypass keywords. Skipping search.")
        return {"rag_documents": [], "metadata": {"rag_failed": False}}

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
        litellm.drop_params = True  # Drop unsupported params (e.g. dimensions on local models)
        emb_resp = await litellm.aembedding(
            model=settings.EMBEDDING_MODEL,  # Configured in .env → litellm_config.yaml
            input=[search_query],
            api_base=settings.LITELLM_API_BASE,
            api_key=settings.LITELLM_API_KEY,
            custom_llm_provider="openai",
            # NOTE: `dimensions` is intentionally omitted — local models (LM Studio) don't
            # support it and raise UnsupportedParamsError. drop_params=True handles cloud models.
        )
        embedding = emb_resp.data[0]["embedding"]
    except Exception as emb_err:
        logger.error(f"RAG: Embedding generation failed — skipping search: {emb_err}")
        return {"rag_documents": [], "metadata": {"rag_failed": True, "rag_error": str(emb_err)}}

    try:
        async with pool.connection() as conn:
            async with conn.cursor() as cur:
                # CTE computes distance once per row — avoids serializing the
                # 768-dim vector 3 times as separate query parameters.
                query = """
                WITH scored AS (
                    SELECT content,
                           1 - (embedding <=> %s::vector) AS similarity_score
                    FROM documents
                )
                SELECT content, similarity_score
                FROM scored
                WHERE similarity_score >= 0.7
                ORDER BY similarity_score DESC
                LIMIT 5;
                """
                await cur.execute(query, (embedding,))
                results = await cur.fetchall()

        # 4. Format results for the Agent
        docs = [row[0] for row in results]

        logger.debug(f"DEBUG RAG: Row count {len(results)}, Docs: {docs}")
        logger.info(f"RAG: Raw results count: {len(results)}")
        
        if not docs:
            logger.info("RAG: No relevant documents found above 0.7 threshold.")
            return {"rag_documents": [], "metadata": {"rag_failed": True}}

        logger.info(f"RAG: Found {len(docs)} relevant documents.")
        # Clear the failed flag if we found something
        return {"rag_documents": docs, "metadata": {"rag_failed": False}}



    except Exception as e:
        logger.error(f"RAG search error: {str(e)}")
        return {"rag_documents": ["Error: Failed to search knowledge base."]}
