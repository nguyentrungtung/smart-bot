# Code Patterns & Strict Rules

## 1. Concurrency (Locking)
- **Session Locking**: In `api/socket_handler.py`, any incoming message MUST generate a Redis Lock (`redis.lock(f"session_{session_id}", timeout=30)`). The `timeout=30` is **mandatory** to prevent zombie locks if the server crashes.
```python
# REQUIRED BOILERPLATE: API Socket Handler
async def handle_message(sid, data):
    session_id = data.get("session_id")
    lock_key = f"lock:{session_id}"
    
    # timeout=30 is CRITICAL to prevent Zombie Locks
    async with redis_client.lock(lock_key, timeout=30, blocking_timeout=2):
        # ... process LangGraph stream ...
```

## 2. Database Connection Management
- **LangGraph Checkpointing**: Do NOT use `AsyncPostgresSaver.create()` blindly per request. 
- You MUST initialize a global connection pool (`psycopg_pool.AsyncConnectionPool`) at app startup and pass this pool to the `MemorySaver`. Failure to pool connections will cause `FATAL: too many clients` crashes.
```python
# REQUIRED BOILERPLATE: main.py / lifespan
from psycopg_pool import AsyncConnectionPool
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

async def lifespan(app: FastAPI):
    # Create Pool ONCE
    async with AsyncConnectionPool(settings.DATABASE_URL, max_size=20) as pool:
        app.state.pool = pool
        app.state.checkpointer = AsyncPostgresSaver(pool)
        yield
```

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
```javascript
// REQUIRED BOILERPLATE: Frontend Preact Widget
import { io } from "socket.io-client";

// Do NOT set extraHeaders: { Authorization... }
const socket = io("https://api.domain.com", {
  auth: {
    token: "JWT_TOKEN_HERE" // Must be validated by backend `auth.py` middleware
  }
});
```

## 5. RAGFlow Integration
- **Isolate Systems**: Do NOT write SQL queries that insert data directly into RAGFlow's postgres database tables from the `core_backend` Celery workers.
- **REST Sync**: You MUST push the conversation logs / `UserProfiles` sync exclusively via RAGFlow's official HTTP REST API.

## 6. Circuit Breakers (External Tools)
- **Fail Open**: Inside `mcp_clients/` communicating with MCP servers (like Xweb creation), if the external HTTP request takes too long or fails, use a `try/except` Circuit Breaker pattern to immediately return an error dictionary to LangGraph, freeing up the connection thread rather than hanging indefinitely.

## 7. Database Migrations & Seeding
- **Alembic Strictness**: Do NOT write pure SQL scripts to create tables or alter schema. You MUST define SQLAlchemy models in python and generate migration files using:
```powershell
# REQUIRED BOILERPLATE: Modifying DB Schema
docker-compose exec core_backend alembic revision --autogenerate -m "added_new_table"
docker-compose exec core_backend alembic upgrade head
```
- **Seeding Test Data**: Whenever you spin up a fresh DB container to test RAG or Memory workflows, you must write and execute `scripts/seed.py`. Do NOT manually insert data via `psql` shell. The seed script should use SQLAlchemy ORM to insert structured mock `UserProfiles` and `pgvector` embeddings natively.

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
