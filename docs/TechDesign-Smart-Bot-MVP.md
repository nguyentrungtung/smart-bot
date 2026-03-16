# Technical Design Document: Smart-Bot MVP

## 1. Recommended Approach
Smart-Bot is built using a decoupled, highly concurrent microservices architecture. The backbone is Python-based (LangGraph, Python 3.11+), enabling stateful Agentic flows that communicate via `python-socketio` for real-time streaming to an embedded JS widget (Preact, within an `iframe`).
- **Core AI Engine**: LangGraph orchestrates complex, cyclical Agent logic and natively manages state.
- **Model Gateway**: LiteLLM sits as an HTTP/REST proxy between the Backend and models, prioritizing local models (LM Studio) and failing over to OpenAI.
- **Data Engine**: A standalone Open Source solution, RAGFlow, runs on a completely separate server for specialized data ingestion, chunking, and evaluation. Once vectors are tested and approved in RAGFlow, a nightly Celery Cronjob synchronizes the high-quality embeddings into the core backend's centralized PostgreSQL instance using the `pgvector` extension. **Standardized Vector Dimension: 768** to ensure full compatibility between local models (LM Studio) and cloud failovers (Gemini/OpenAI).
- **External Tooling**: External system interactions (like Xweb creation) are decoupled into independent Model Context Protocol (MCP) servers. The backend uses a unified **Resilience MCP Client** with a built-in circuit breaker to handle all external communication.
- **Local Tooling**: Simple, logic-only tools (Time, File operations, User Profile DB updates) are executed directly in the backend using a specialized **Local Tools** connector to minimize network latency.
- **Token Management**: Strict token counting and summarization logic is implemented to handle the smaller context windows of local models (e.g., LM Studio at 4096 tokens). The system uses an aggressive **Hybrid Memory** strategy (Summarization + Sliding Window) to prevent context overflows.

## 2. Alternative Options Considered
- **Direct LLM Tooling vs. MCP**: *Considered* having the LLM directly call internal Python scripts. *Rejected* because it heavily couples the core AI engine to internal company software APIs. The chosen MCP standard allows language-agnostic, easily deployable microservice tools.
- **LangChain RAG vs. Standalone RAGFlow**: *Considered* building chunking/embedding logic directly in the core LangGraph state. *Rejected* to reduce backend complexity. RAGFlow offloads heavy data-preprocessing logic.
- **Single DB vs Polyglot Persistence**: *Considered* separate vector DBs (Pinecone/Milvus) and state DBs (Redis/Mongo). *Rejected* for the MVP; a single powerful PostgreSQL instance with `pgvector` handles both LangGraph state (`MemorySaver`), long-term user profiles, and embeddings, heavily reducing operational overhead.

## 3. Project Setup
The project relies heavily on Docker Compose to orchestrate its many decoupled microservices. Every discrete component (Core Backend, LiteLLM proxy, each MCP Server) lives in its own container.

```bash
# Example Setup Strategy
git clone <repo>
cd smart-bot

# Start core infrastructure (Postgres, Redis, RAGFlow, LiteLLM)
docker-compose --profile infra up -d

# Start MCP Servers
docker-compose --profile tools up -d

# Start Core AI Backend & Celery Workers
docker-compose --profile backend up -d

# Run Database Migrations (Initialize tables inside container)
docker-compose exec core_backend alembic upgrade head

# Seed Initial Mock Data (RAG, Admin User)
docker-compose exec core_backend python scripts/seed_db.py

# Maintenance: Clear memory (Long-term, Short-term, or All)
# To clear LangGraph Checkpoints (checkpoints, checkpoint_writes, checkpoint_blobs): 
# docker-compose exec core_backend python scripts/clear_memory.py --short-term
docker-compose exec core_backend python scripts/clear_memory.py --all
```

## 4. Feature Implementation Details
- **Resilient Tool Execution (Circuit Breaker Pattern)**: For long-running or failure-prone actions (like creating an Xweb instance), the MCP Servers implement a Circuit Breaker design pattern. If the external Xweb API is overloaded or unreachable, the MCP server quickly fails open and returns a user-friendly error (e.g., "Network error, please try again in 1 minute") instead of hanging the SSE connection indefinitely. This allows immediate connection release and feeds directly into external monitoring/alerting systems.
- **Multimodal Chat (Voice/Vision) & Auto-Detection**: 
  - **Auto-Detection Logic**: The system automatically detects capabilities (Vision, Audio) based on the `LLM_MODEL` name or `.env` override (`MULTIMODAL_ENABLED`). Gemini 2.5-flash enables these features by default.
  - **Refactored Architecture**: All media processing is consolidated in the `app/multimodal` package.
  - **Native Multimodal (Gemini 2.5)**: The implementation leverages Gemini 2.5's native multimodal capabilities. Audio and images are sent as `base64` fragments within standard content blocks. 
  - **Vision**: `MultimodalProcessor` converts images into LiteLLM `image_url` blocks.
  - **Voice**: Supports both native `input_audio` blocks for Gemini and explicit STT (Whisper) via LiteLLM if the model requires pre-transcribed text.
- **WebSocket Reconnection & Message Recovery**: To handle mobile networks or brief disconnects, the JS Widget implements a robust connection recovery strategy. If the WebSocket drops, the client automatically reconnects and passes a `last_message_id` payload. The `socket_handler` backend queries the active LangGraph/Redis state and instantly re-streams any tokens or messages the user missed during the exact window of disconnection.
- **Agentic Reasoning UI (`<thinking>` tags) & Concurrency Locks**: 
  - System prompts instruct the model to wrap its internal tool selection and scratchpad reasoning in `<thinking>` tags. 
  - `api/socket_handler.py` parses these tokens from the LangGraph stream on-the-fly, redirecting them to a separate `thought_stream` event. The Preact frontend renders this stream inside a permanent, collapsible Accordion component that persists in the chat history. **This provides full transparency of the AI's reasoning even after the conversation moves forward.**
  - **Premium Aesthetics**: The UI uses a "White/Blue" theme (White background, Slate-Blue borders, Black text) for high readability and a professional enterprise feel.
  - **Session Locking (w/ Anti-Zombie TTL)**: To prevent Race Conditions (users spamming messages while the AI is thinking), a strict implementation of **Session Locks** is enforced. The Frontend disables the input box visually, and the Backend uses a `Redis Lock` bound to the user's `session_id` inside `api/socket_handler.py`. Crucially, this lock MUST have a defined TTL (Time-To-Live, e.g., `timeout=30s`) so that if the backend crashes mid-generation, the lock expires automatically and prevents "Zombie Locks" that permanently ban the user. Any messages sent while the lock is active are rejected or queued until the current AI stream fully completes.
- **Human-In-The-Loop (HITL) via Telegram**: Crucial, sensitive node executions (e.g., executing the "deploy" pipeline inside the Xweb MCP server) use LangGraph's `.compile(interrupt_before=["xweb_tool"])` feature. 
  - When paused, the backend generates a Request UUID and sends a notification message containing the UUID to a predefined **Telegram chat/bot**.
  - **Approval Pipeline**: A human manager can either:
    1. Go to the parent website's Admin Portal, which hits a REST API endpoint (`/api/v1/hitl/approve/{uuid}`) to resume the LangGraph execution.
    2. *Fast Bypass*: Reply directly in the Telegram chat (e.g., "Approve {uuid}"). A webhook listener in the backend catches this, automatically hits the API, and resumes the action instantly without needing to log in to the portal.
- **Widget Authentication & Personalized Memory**:
  - **Secure Auth Injection (Socket IO Payload)**: To identify users for personalization, the parent website securely passes an encrypted **JWT token** to the `iframe` via `postMessage`. Because browser-based WebSockets natively block custom HTTP Headers during the connection handshake, the frontend widget MUST pass the token explicitly in the `auth` payload object (e.g., `io(url, { auth: { token: "JWT" } })`). The backend drops any connection missing this payload.
  - **JWT Keypair Encryption (RS256) & Bcrypt Hashing**: Authentication is managed natively within the Smart-Bot project. The Python backend generates an **RS256 Keypair** for JWT signing and uses `passlib` with `bcrypt` for secure password hashing in the `users` table. Primary `admin` credentials are seeded for development and testing.
  - **postMessage Origin Security**: To prevent arbitrary websites from embedding the iframe and injecting fake authentications via `postMessage`, the Preact application MUST hardcode a strict `event.origin` whitelist check before processing any incoming messages.
  - **PII Scrubber Middleware**: Before any user message leaves the backend to hit LiteLLM, it passes through `middleware/pii_scrubber.py`. Using strict Regex rules, sensitive data (Phone numbers, Passwords, Credit Cards) is replaced with `[REDACTED]` or `*****` to prevent PII leakage to cloud models and protect the raw logs in the `Conversations` table.
  - **Short-Term Memory (Persistent)**: LangGraph state is persisted using `AsyncPostgresSaver` bound to the `thread_id`. This ensures that even if the backend container restarts, the AI "remembers" the current conversation context (Short-term memory).
  - **Strict Server-side Session Initialization**: To ensure data consistency, the Frontend must never generate random `session_id`s. If no session exists in `localStorage`, the widget calls `POST /api/v1/chat/new-session` to receive an authoritative UUID generated and registered by the backend in the `session_metadata` table.
  - *Long-Term Profile*: User-specific facts (Name, preferences) are managed via the `update_user_profile` tool. The system proactively calls this tool whenever a user provides personal details. Data is persisted in the `user_profiles` table using explicit PostgreSQL transactions (`async with conn.transaction()`) to ensure absolute data reliability and eliminate race conditions during high-concurrency LTM updates.
  - *Raw Conversation Persistence*: The exact, unadulterated dialogue transcripts are archived indefinitely in a dedicated `Conversations` table. This forms the foundational dataset for the continuous learning feedback loop. A separate async worker embeds these conversations via RAGFlow, actively increasing the bot's enterprise knowledge base from massive user interactions. **CRITICAL API DECOUPLING:** The Celery worker MUST push these transcripts exclusively via **RAGFlow's Official REST API** (using pagination to avoid memory crashes). Direct SQL inserts into RAGFlow's internal database are strictly forbidden to ensure schema independence.

## 5. Database, Storage, & Migrations
- **PostgreSQL 16 (with `pgvector`)**: The central nervous system. 
  - Schema includes tables for RAGFlow vectors, LangGraph thread state checkpoints (`checkpoints`, `checkpoint_writes`, `checkpoint_blobs`), Long-Term Memory (UserProfiles), and raw Conversation Archives.
  - *Note on LangGraph Memory Deletion*: LangGraph offloads large state data into `checkpoint_blobs` which references `checkpoints`. When programmatically deleting a session, delete from `checkpoint_blobs`, `checkpoint_writes`, and `checkpoints` using independent database transactions to avoid Foreign Key violation aborts.
  - **Versioning Vectors (Embedding Drift)**: The RAG Postgres schema explicitly includes an `embedding_version_id` column. When the embedding algorithm is upgraded in the future, the backend will only query vectors matching the active version ID, ensuring RAG search results never degrade into chaos due to model upgrade drift.
  - **Standardized Migrations**: All database schema changes are strictly managed using **Alembic** (the standard for SQLAlchemy). This prevents schema drift between developers/AI agents and ensures that applying new features (like adding a new profile field) is automatically version-controlled and reproducible across environments. Agents MUST run `alembic revision --autogenerate -m "..."` whenever `models.py` changes.
  - **Database Seeding**: A dedicated script (`scripts/seed.py`) is required to populate the database with baseline test data (e.g., mock UserProfiles, dummy Vector embeddings) after a fresh Docker spin-up, ensuring the AI can immediately test RAG workflows without manually inserting data.
- **Redis (Secure & Stateful)**: Acts as a heavily utilized multi-tool with mandatory password authentication (`REDIS_PASSWORD`). It manages high-speed semantic caching, operates as the fast message broker, and handles user session lifecycle states.

## 6. AI Assistance Strategy & Prompts
- Centralized inside `core_backend/app/prompts/`.
- **System Instructions**: Highly detailed templates instructing the agent to utilize RAG data first, and only call external MCP tools if authorized context matches.
- **RAG Hallucination Prevention & Cosine Similarity**: LangGraph enforces a strict conditional edge based on `pgvector` scores. The SQL query MUST explicitly use the **Cosine Similarity operator (`<=>`)** so that higher scores accurately represent closer matches. If the best match scores below a defined `0.7` Threshold (Confidence Score), the AI bypasses generation entirely and triggers a hardcoded fallback: *"Xin lỗi, tôi chưa rõ tài liệu này. Vui lòng để lại SĐT / Email để nhân viên CSKH hỗ trợ bạn."*
- All template strings are populated dynamically at runtime with context pulled from the `UserProfiles` table to enhance the local LM Studio model's conversational ability to "know" who it is talking to.

## 7. Deployment Plan
- **Infrastructure**: Scalable VPS (e.g., AWS EC2, DigitalOcean Droplets) capable of vertical scaling (RAM for heavy Postgres usage, CPU for high CCU WebSocket connections).
- **API Gateway**: Nginx/Traefik routing requests (`/api/v1/`, `/socket.io/`, `/tools/`) to the appropriate Docker containers.
- **Frontend Widget (Iframe Responsive Resizing)**: The compiled Preact JS bundle is hosted on a high-availability CDN. The parent website embeds a lightweight `<script>` tag that injects the `iframe`. 
  - *Dynamic Sizing & Layout Control*: The iframe and parent script establish a **2-way `postMessage` bridge**. The iframe continuously measures its internal DOM height and broadcasts it to the parent script, which smoothly resizes the `iframe` container.
  - **Advanced Resizing Features**: The widget includes a "Maximize/Restore" toggle for full-screen focus and a **flexible resize handle** (top-left) that allows users to manually drag and adjust the chat window dimensions.
  - **WebSocket Security (CORS Bypass Prevention)**: Because WebSockets can bypass Nginx CORS, the backend `python-socketio` initialization (`sio = socketio.AsyncServer()`) MUST strictly dynamically load `cors_allowed_origins` from the `config.yaml` environment variables (e.g., `['https://production-site.com', 'http://localhost:3000']`). It must never be set to the insecure wildcard `*`.

## 8. Development & Cost Breakdown (Estimates)
- **Local Dev**: Free (Local LM Studio for LLMs, open-source Postgres/Redis).
- **Production Infrastructure**: ~$50-100/mo (Scaled 8GB+ RAM VPS for DB, Broker, and Python backends).
- **API Usage**: Heavily reduced by prioritizing local LM Studio and using Redis semantic caching at the LiteLLM proxy layer. Fallback to OpenAI API will incur standard low-latency usage costs.

## 9. Scaling Path
- **Vertical -> Horizontal**: If WebSocket connections reach capacity, the underlying `python-socketio` can natively scale out horizontally using Redis as its pub/sub message queue manager, allowing multiple backend instances to handle thousands of concurrent chats seamlessly.
- **Automatic LiteLLM Failover**: To prevent the "bottleneck" of high concurrency hitting the local LM Studio instance, `config.yaml` is configured with strict LiteLLM proxy **Routing Strategies** (e.g., `num_retries`, `fallbacks`, `rpm` limits). If the local LM Studio model queue backing up, the proxy automatically, invisibly routes the overflow traffic to the high-concurrency cloud provider (OpenAI `gpt-4o`), guaranteeing zero latency spikes for users without any manual intervention.
- **RAG Refinement**: Dedicated separate Vector databases (Milvus) can be implemented if the Postgres table swells to excessive sizes.

## 10. Limitations
- Security relies entirely on the HTTP API Gateway rules and the `iframe` browser security model (`postMessage` origin enforcement); any failure in the Nginx config could expose internal MCP tool routes.
