# Technical Design Document: Smart-Bot MVP

## 1. Recommended Approach
Smart-Bot is built using a decoupled, highly concurrent microservices architecture. The backbone is Python-based (LangGraph, Python 3.11+), enabling stateful Agentic flows that communicate via `python-socketio` for real-time streaming to an embedded JS widget (Preact, within an `iframe`).
- **Core AI Engine**: LangGraph orchestrates complex, cyclical Agent logic and natively manages state.
- **Model Gateway**: LiteLLM sits as an HTTP/REST proxy between the Backend and models, prioritizing local models (LM Studio) and failing over to OpenAI.
- **Data Engine**: A standalone Open Source solution, RAGFlow, runs on a completely separate server for specialized data ingestion, chunking, and evaluation. Once vectors are tested and approved in RAGFlow, a nightly Celery Cronjob synchronizes the high-quality embeddings into the core backend's centralized PostgreSQL instance using the `pgvector` extension. **Standardized Vector Dimension: 768** to ensure full compatibility between local models (LM Studio) and cloud failovers (Gemini/OpenAI).
- **External Tooling**: External system interactions (like Xweb creation) are decoupled into independent Model Context Protocol (MCP) servers. The backend uses a unified **Resilience MCP Client** with a built-in circuit breaker to handle all external communication.
- **Local Tooling**: Simple, logic-only tools (Time, File operations, User Profile DB updates) are executed directly in the backend using a specialized **Local Tools** connector to minimize network latency.
- **Token Management**: Strict token counting and summarization logic is implemented. The system uses an aggressive **Hybrid Memory** strategy (Summarization + Sliding Window). Summarization triggers when `tokens > SUMMARY_THRESHOLD` OR `message_count > MAX_HISTORY_MESSAGES` (default: 10).
- **End-to-End Tracing**: Every request turn generates a unique `interaction_id`, which is propagated through LangGraph and injected into all logs using `contextvars`, allowing for precise debugging across distributed nodes.

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
  
  - **Vision Pipeline**: `MultimodalProcessor` converts base64 images into LiteLLM `image_url` blocks (data URI format). Images are validated for size (< 4MB) before sending to model. After generation, `vision_scrubber` node optionally replaces images with text descriptions to save tokens in future turns.
  
  - **Voice/Audio Pipeline (Server-Side STT — Community Standard)**:
    - **Why STT-First?** Model-agnostic approach (works with all LLM backends: LM Studio, Gemini, OpenAI). Avoids input_audio format fragmentation (OpenAI Realtime vs Gemini Live vs local models). Transcription is auditable and can be logged/reviewed.
    - **Architecture**: Browser captures audio (webm/ogg/mp4) → base64 encode → Socket.IO → Backend processes in 4 steps
    - **Step 1 — DECODE**: base64 string → raw audio bytes via `base64.b64decode()`
    - **Step 2 — CONVERT**: FFmpeg pipe (async subprocess) converts any format → 16kHz mono PCM s16le. Zero temp files; all I/O via stdin/stdout pipes (memory-only pipeline)
    - **Step 3 — PARSE**: numpy `frombuffer` (raw bytes → float32 array, normalized [-1.0, 1.0])
    - **Step 4 — TRANSCRIBE**: faster-whisper (SYSTRAN, 21.9k⭐) Vietnamese STT
      - Runs in thread executor (CPU-bound, non-blocking event loop)
      - Lazy-loads model on first call (~10s delay), then cached in memory
      - Configuration: `language="vi"`, `vad_filter=True` (eliminates silence), `beam_size=5`, `condition_on_previous_text=False`
      - **Language Confidence Filter**: If `language_probability < 0.5`, returns empty string (rejects noise, silence, wrong language hallucinations)
    - **Output Injection**: Transcription injected as text block: `[Giọng nói của người dùng]: {transcribed_text}` → passed to LLM as part of user message
    - **Error Handling**: 
      - Audio too short (< 300ms) → `[Giọng nói quá ngắn]`
      - FFmpeg timeout (> 30s) → `[Lỗi xử lý audio (quá lâu)]`
      - STT timeout (> 30s) → `[Lỗi nhận diện giọng nói (quá lâu)]`
      - Low confidence → `[Không nhận diện được giọng nói]` (empty transcription passed through)
- **WebSocket Reconnection & Message Recovery**: To handle mobile networks or brief disconnects, the JS Widget implements a robust connection recovery strategy. If the WebSocket drops, the client automatically reconnects and passes a `last_message_id` payload. The `socket_handler` backend queries the active LangGraph/Redis state and instantly re-streams any tokens or messages the user missed during the exact window of disconnection.
- **Agentic Reasoning UI (`<thinking>` tags) & Concurrency Locks**: 
  - System prompts instruct the model to wrap its internal tool selection and scratchpad reasoning in `<thinking>` tags. 
  - `api/socket_handler.py` parses these tokens from the LangGraph stream on-the-fly, redirecting them to a separate `thought_stream` event. The Preact frontend renders this stream inside a permanent, collapsible Accordion component that persists in the chat history. **This provides full transparency of the AI's reasoning even after the conversation moves forward.**
  - **Premium Aesthetics**: The UI uses a "White/Blue" theme.
  - **Interaction Tracing & Structured Logging**: The backend implements `interaction_id` tracing and JSON-structured logging. Logs capture the full lifecycle of a request, including RAG search results, node transitions, and LLM prompts (when `LOG_LEVEL=DEBUG`).
  - **Session Locking (w/ Anti-Zombie TTL)**: To prevent Race Conditions...
- **Human-In-The-Loop (HITL) via Telegram**: Crucial, sensitive node executions (e.g., executing the "deploy" pipeline inside the Xweb MCP server) use LangGraph's `.compile(interrupt_before=["xweb_tool"])` feature. 
  - When paused, the backend generates a Request UUID and sends a notification message containing the UUID to a predefined **Telegram chat/bot**.
  - **Approval Pipeline**: A human manager can either:
    1. Go to the parent website's Admin Portal, which hits a REST API endpoint (`/api/v1/hitl/approve/{uuid}`) to resume the LangGraph execution.
    2. *Fast Bypass*: Reply directly in the Telegram chat (e.g., "Approve {uuid}"). A webhook listener in the backend catches this, automatically hits the API, and resumes the action instantly without needing to log in to the portal.
- **Widget Authentication & Personalized Memory**:
  - **Secure Auth Injection & Status UI**: To identify users, the parent website securely passes an encrypted **JWT token** to the `iframe` via `postMessage`. 
    - **Status Dot Indicator**: The widget header includes a real-time status indicator (**Green**: Connected, **Red**: Auth Error).
    - **Restricted Login**: Guest login without a password is disabled; authentication strictly verifies credentials against the `users` table.
  - **JWT Keypair Encryption (RS256) & Bcrypt Hashing**: Authentication is managed natively within the Smart-Bot project. The Python backend generates an **RS256 Keypair** for JWT signing and uses `passlib` with `bcrypt` for secure password hashing in the `users` table. Admin and user accounts are seeded for testing.
  - **postMessage Origin Security**: To prevent arbitrary websites from embedding the iframe and injecting fake authentications via `postMessage`, the Preact application implements a strict `SMART_BOT_AUTH` type check and origin whitelist.
  - **PII Scrubber Middleware**: Before any user message leaves the backend to hit LiteLLM, it passes through `middleware/pii_scrubber.py`.
  - **Short-Term Memory (Persistent)**: LangGraph state is persisted using `AsyncPostgresSaver`.
  - **Strict Server-side Session Initialization**: To ensure data consistency, the Frontend calls `POST /api/v1/chat/new-session`.
  - *Long-Term Profile*: User-specific facts (Name, preferences) are managed via the `update_user_profile` tool.
  - *Raw Conversation Persistence & RAG Support*: Conversations are archived for learning. The `documents` table MUST contain both `content` (String) and `embedding` (Vector 768) columns for RAGFlow/RAG searching. Missing embeddings will result in RAG bypass.

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

## 10. Voice/Audio Chat Testing & Validation

### Test Suite: `test_voice_chat.py`
Located at `core_backend/scripts/test_voice_chat.py`. Validates the complete audio pipeline end-to-end with 7 turns (4 voice, 3 text) in Vietnamese.

**Test Scenario**:
- T1 (VOICE): Synthetic audio greeting → AI gracefully asks to repeat if STT fails
- T2 (TEXT): AI identity question → RAG response about SmartSales Assistant
- T3 (VOICE+TEXT): "mấy giờ rồi" (time query) → tool call + response with current time
- T4 (VOICE+TEXT): "thời tiết hà nội" (weather) → tool call with location parameter
- T5 (TEXT): "Tôi tên là Minh..." → profile seeding, AI acknowledges
- T6 (VOICE+TEXT): "smart bot có những tính năng gì" → RAG search about product features
- T7 (TEXT): "Bạn có nhớ tên tôi không?" → memory recall, AI should answer "Minh"

**Execution**:
```bash
docker compose exec core_backend python scripts/test_voice_chat.py
```

**Expected Output**: 7/7 PASS. Verifies:
- Audio pipeline steps [1/4] DECODE → [4/4] TRANSCRIBE in backend logs
- Streaming chunks arrive with `chunk` key (not `content`)
- Guard bypass responses are streamed (no empty responses)
- Profile extraction works (name stored and recalled)
- Session lock releases immediately after `message_complete` (background nodes drain separately)

### Audio Pipeline Gotchas for Developers

1. **Synthetic Audio for Testing**: Sine waves at 440Hz will NOT transcribe (language confidence < 0.5). This is CORRECT behavior — the pipeline is rejecting non-speech audio. For real transcription testing, use pre-recorded Vietnamese WAV clips or actual user voice.

2. **Faster-Whisper Model Loading**: First audio message in a session will take ~10s if model hasn't been pre-warmed. The backend now pre-warms the model at startup (via `main.py`'s `_prewarm_whisper()`). If you see 30s+ delays on first message, check that `✅ faster-whisper model pre-warmed and ready.` appears in startup logs.

3. **FFmpeg Pipe I/O**: The pipeline uses `asyncio.create_subprocess_exec` with stdin/stdout pipes. FFmpeg MUST be installed on the system. The binary is detected via `PATH`. Test with: `which ffmpeg` or `ffmpeg -version`.

4. **Socket Event Key Convention**: Streaming uses `{"chunk": "..."}` throughout. Messages, thoughts, and responses all follow this pattern. Do NOT change to `{"content": "..."}` without updating all emitters and receivers.

5. **Streaming Fragment Handling**: Tools-call tokens or other patterns may arrive split across multiple `message_stream` events. Use `re.sub()` with pattern stripping on each chunk, not `fullmatch()` (which only works for complete tokens).

6. **Language-Specific VAD**: The VAD (Voice Activity Detection) filter is tuned for Vietnamese with `min_silence_duration_ms=300` and `speech_pad_ms=200`. Adjust if testing other languages.

7. **Guard Bypass Response Streaming**: When the guard node returns a fallback message, it MUST be streamed via `message_stream` event before `message_complete`. Otherwise, the response appears empty on the client. This is now handled in `generate.py` line 53.

### Known Model Quirks (LM Studio Local)

- **Tool-Call Token Leak**: LM Studio outputs raw `<|tool_call>call:TOOL_NAME{...}<|tool_call|>` tokens even when tools are not provided (`use_tools=None`). The stream handler now strips these via regex before emitting to the client.
- **Template Substitution**: Some LM Studio models respond with template placeholders like `{{get_current_time()}}` instead of actually executing tool calls. This is a model training limitation, not a backend bug. Workaround: ensure the tool description is clear and the model is properly fine-tuned, or accept the placeholder and handle gracefully in the UI.
- **Slow Response**: Local LM Studio models run on CPU (no GPU). Response generation for longer outputs (> 500 tokens) may take 30-60s. Set `TURN_TIMEOUT=240s` to accommodate.

---

## 11. Limitations
- Security relies entirely on the HTTP API Gateway rules and the `iframe` browser security model (`postMessage` origin enforcement); any failure in the Nginx config could expose internal MCP tool routes.
- Audio STT pipeline depends on FFmpeg binary and faster-whisper availability; if either is missing, audio messages will fail gracefully with error text.
- Local LM Studio model performance is CPU-bound; GPU acceleration is not currently configured. High concurrency (100+ users) will require horizontal scaling via Redis pub/sub or fallover to cloud LLM (Gemini/OpenAI).
