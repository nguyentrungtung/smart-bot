# Code Patterns & Strict Rules

## 1. Concurrency (Locking)
- **Session Locking**: In `api/socket_handler.py`, any incoming message MUST generate a Redis Lock (`redis.lock(f"session_{session_id}", timeout=30, blocking_timeout=2)`). The `timeout=30` is **mandatory** to prevent zombie locks if the server crashes, and `blocking_timeout=2` minimizes blocked process queues during high concurrency workflows.
```python
# REQUIRED BOILERPLATE: API Socket Handler
async def handle_message(sid, data):
    session_id = data.get("session_id")
    interaction_id = str(uuid.uuid4()) # REQUIRED: Generate tracing ID
    
    # Set context for structured logging
    session_id_context.set(session_id)
    interaction_id_context.set(interaction_id)

    async with session_lock(redis_client, session_id, timeout=30) as acquired:
        if not acquired: return
        # ... process LangGraph stream ...
```

## 2. Persistent Memory (PostgreSQL Checkpointer)
- **Persistence Across Restarts**: To ensure the AI remembers past conversation turns even after a server restart, you MUST use `AsyncPostgresSaver` with a valid `thread_id`.
- You MUST initialize a global connection pool (`psycopg_pool.AsyncConnectionPool`) at app startup and pass this pool to the saver.
```python
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
# Initialize once in app lifespan
checkpointer = AsyncPostgresSaver(pool)
graph = workflow.compile(checkpointer=checkpointer)
```
- **Line-by-Line Interaction History**: You MUST log every single incoming user message and outgoing AI message (along with any UI ratings/feedback) into the `chat_interactions` table using `ChatHistoryTracker` within the API/Socket handlers. This ensures full traceability outside the blackbox of LangGraph's checkpointer.

## 3. RAG Search (pgvector)
- **Cosine Operator**: When executing pgvector SQL queries in `nodes/rag_search.py`, YOU MUST use the Cosine Similarity operator (`<=>`).
```sql
-- REQUIRED BOILERPLATE: SQL Query for pgvector
SELECT content, 1 - (embedding <=> :query_embedding) AS similarity_score
FROM documents
WHERE 1 - (embedding <=> :query_embedding) >= 0.7
ORDER BY embedding <=> :query_embedding
LIMIT 5;
```
- **Confidence Rule**: Do NOT allow the AI to hallucinate. If the SQL query returns no results (because nothing scored `>= 0.7`), you must use a conditional edge to branch to a fallback error message *"Xin lỗi, tôi chưa rõ tài liệu này..."* instead of proceeding to generation.

## 4. WebSocket Security
- **Strict CORS**: Do NOT use `socketio.AsyncServer(cors_allowed_origins="*")`. This defeats the iframe isolation. The `cors_allowed_origins` must load a strict list of domains from the backend environment variables (`config.yaml`).
- **Authentication**: Do NOT use HTTP Headers for WebSocket connection auth. Browser WebSockets drop them. Pass the JWT payload explicitly inside the `auth` object.
- **JWT Signature (RS256)**: The backend must generate an RSA keypair. It issues JWT tokens signed with the **Private Key** containing required metadata claims (`sub`, `name`, `role`). Expiration times must be dynamically driven implicitly via `.env` (`JWT_ACCESS_TOKEN_EXPIRE_MINUTES`). The `auth.py` middleware MUST use `PyJWT` with the `RS256` algorithm to decode the token using the corresponding **Public Key**.
```javascript
// REQUIRED BOILERPLATE: Frontend Preact Widget
import { io } from "socket.io-client";

// Do NOT set extraHeaders: { Authorization... }
const socket = io("https://api.domain.com", {
  auth: {
    token: "JWT_TOKEN_HERE" // Must be validated by backend `auth.py` middleware via Public Key RS256
  }
});
```

## 5. RAGFlow Integration
- **Isolate Systems**: Do NOT write SQL queries that insert data directly into RAGFlow's postgres database tables from the `core_backend` Celery workers.
- **REST Sync**: You MUST push the conversation logs / `UserProfiles` sync exclusively via RAGFlow's official HTTP REST API.

## 6. Circuit Breakers (External Tools)
- **Unified Resilience**: All external MCP tool calls MUST use the `app.connectors.mcp.client.call_mcp_tool` wrapper.
- **Circuit Breaker**: This client utilizes a named circuit breaker (`mcp_resilience_client`). If the MCP server is down or timing out, the circuit will trip, immediately returning an error dict to LangGraph to prevent hanging the main execution thread.
- **Fail Open**: LLM should be informed of the failure via the returned error dictionary so it can apologize gracefully or suggest an alternative.

## 7. Local vs External Tools
- **Split Responsibility**: Never call internal backend maintenance (Time, Files, User Profile updates) via MCP. These belong in `app.connectors.local_tools.py`.
- **Registry**: Both local and external tools are managed via the unified `execute_tools` node. Any tool NOT specified in the `LOCAL_TOOL_REGISTRY` will be automatically routed to the MCP client.

## 7. Database Migrations & Seeding
- **Alembic Strictness**: Do NOT write pure SQL scripts to create tables or alter schema in production. Make sure SQLAlchemy models are defined first.
- **Seeding Test Data**: Whenever you spin up a fresh DB container to test workflows, you must write and execute `scripts/seed_db.py`. Do NOT manually insert data via `psql` shell. The seed script should use SQLAlchemy ORM/Core to create tables like `documents`, `user_profiles`, and `chat_interactions` and populate them natively.

## 8. Widget Security (postMessage XSS Prevention)
- **Strict Origin Checking**: When listening for dynamic resize or JWT Auth messages from the parent window in the Preact app, you MUST explicitly verify the `event.origin`.
```javascript
// REQUIRED BOILERPLATE: Preact Iframe App
window.addEventListener("message", (event) => {
    const allowedOrigins = ["https://your-company.com", "http://localhost:3000"];
    if (!allowedOrigins.includes(event.origin)) {
        console.warn("Blocked unrecognized postMessage origin:", event.origin);
        return; 
    }
    // Process event.data...
});
```

## 9. RAGFlow Data Synchronization (Celery Cron)
- **Nightly Sync Job**: You must utilize Celery's `beat_schedule` to trigger the vector synchronization task nightly (e.g., at 2 AM). 
- **Pagination**: When pulling from RAGFlow's REST API into PostgreSQL `pgvector`, the Celery worker MUST use pagination to prevent Out-Of-Memory (OOM) crashes on large datasets.

## 10. Real-time Streaming & Tool Calls
- **Streaming Handlers**: The AI generation node MUST utilize `litellm.acompletion` with `stream=True`. 
- **Token Parsing Workflow**: To prevent `<thinking>` tags and raw JSON arguments from leaking visually into standard message channels, the node MUST act as a **Stateful Token Parser**.
  - Accumulate partial `tool_calls` iteratively across stream chunks (`tc.index`, `tc.id`, `tc.function.arguments`).
  - Scan buffers for explicit delimiters (`<thinking>...</thinking>`).
  - Actively emit `message_stream` for final text output, and `thought_stream` exclusively for filtered reasoning blocks using `sio.emit()` mapped back to the active LangGraph thread context.

## 11. Resilience & Retries
- **LLM Reliability**: All LiteLLM calls in nodes MUST be wrapped with `@async_retry`.
- **Circuit Breaker**: Use `get_circuit_breaker()` for high-risk external integrations.

## 12. Context Truncation (Smart Summarizer)
- **Multi-Trigger**: The summarizer MUST check both `estimate_tokens(messages)` and `len(messages)`. 
- **Thresholds**: Defaults are typically `300 tokens` or `10 messages`.

## 12. Multimodal Processing (Image & Voice)
- **Native Data Flow**: For models like Gemini 2.5-flash, send media as `base64` fragments inside the content array. Use `app/multimodal/processor.py` to standardize FE payloads into LiteLLM blocks.
- **Auto-Detection**: Use `app/multimodal/capabilities.py` to toggle UI features based on the model name.
- **CRITICAL**: When converting `HumanMessage` to LiteLLM payload in `generate.py`, DO NOT use `str(msg.content)` if it is a list (multimodal). Pass the list as-is.

## 13. UI Aesthetics & Responsiveness
- **Theme**: Stick to the professional "White/Blue" theme. Avoid generic colors.
- **Thinking Blocks**: Thinking blocks (`<thinking>`) must be permanent and collapsible in the chat history to allow users to audit the AI's logic at any time.
- **Resizing**: Always implement a flexible resize handle and a Maximize toggle to ensure the widget is accessible across different parent site layouts.
