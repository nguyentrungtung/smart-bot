# Smart-Bot Architecture Research and Design

## 1. Project Overview
Smart-Bot is a highly scalable, 24/7 AI-powered chatbot platform designed for both customer-facing (lead generation and sales) and internal employee assistance. It advises users on enterprise products (ISO certificates, Xweb auto-website builder, POS, CRM) and executes complex actions like automatic website creation and order checking.

### Core Objectives
1. **Intelligent Advising**: Provide accurate product information for enterprise solutions.
2. **Action Execution**: Execute agentic workflows (e.g., website creation, data retrieval).
3. **Multimodal Interactions**: Support Voice (Speech-to-Text and Text-to-Speech) and Vision (Image upload and analysis) capabilities for dynamic user experiences.
4. **Advanced Memory**: Maintain short-term session state and long-term user profiles (name, behavior, preferences) for deep personalization.
5. **Human-in-the-Loop (HITL)**: Pause execution for human confirmation on sensitive actions (e.g., financial transactions).
6. **Self-Improvement**: Analyze interactions to dynamically improve its knowledge base.

---

## 2. Decoupled Microservice Architecture

The architecture follows a strict decoupled microservices pattern communicating primarily over HTTP/REST, with WebSocket (Socket.IO) for real-time frontend communication.

### High-Level Component Diagram
```mermaid
graph TD
    User([End User]) --> |HTTPS / WSS (Text/Audio/Image)| Widget[Isolated JS Widget (iframe)]
    Widget --> |HTTPS / WSS| API_Gateway[Nginx/Traefik API Gateway]
    
    API_Gateway --> |HTTP/WS| Backend[Core LangGraph Backend]
    
    Backend <--> |REST API| LLM_Gateway[LiteLLM Proxy]
    LLM_Gateway <--> |REST API| External_LLMs[(Gemini, OpenAI, Claude)]
    LLM_Gateway <--> |API Context| Vision_Audio_Models[(STT, TTS, Vision APIs)]
    LLM_Gateway <--> |Cache| Redis[(Redis Cache)]
    
    Backend <--> |SSE (MCP)| Tools[MCP Tool Servers]
    Tools <--> |REST API| App_Services[(XWeb, POS, CRM)]
    
    Backend <--> |HTTP| RAG_Service[RAGFlow]
    RAG_Service <--> |SQL/Vector| Postgres[(PostgreSQL + pgvector)]
    
    Backend <--> |PubSub/State| Redis
    Backend <--> |Async Tasks| Celery[Celery Workers]
    Celery <--> |State| Postgres
```

---

## 3. Technology Stack Breakdown & Implementation Details

### 3.1 Frontend Widget (Security First & Multimodal)
- **Technology**: Vanilla JS / Preact (for small bundle size) within an `iframe`.
- **Media Capabilities**: Native browser APIs (`MediaRecorder` for capturing voice, `FileReader` for image uploads) seamlessly built into the UI.
- **Delivery**: CDN-hosted script that injects an `iframe`.
- **Security**:
  - `iframe` enforces strict cross-origin isolation.
  - The parent website cannot read the `iframe` DOM, preventing malicious scripts from stealing chat history or session tokens.
  - CORS configuration on the backend exclusively allows the `iframe` origin.

### 3.2 Main Backend (LangChain v1.2.0+, Python 3.11+, LangGraph)
- **Core Framework**: LangChain + LangGraph for managing stateful, cyclic agent workflows.
- **Real-time Comms**: `python-socketio` (ASGI) for handling WebSocket streaming of LLM tokens, as well as receiving audio streams and transmitting Text-to-Speech (TTS) binary data to the frontend.
- **Multimodal Pipeline**: 
  - **Vision**: Converts uploaded images to Base64 and embeds them into LangChain's `HumanMessage` structures for Vision-capable LLMs (e.g., `gpt-4o`, `claude-3-5-sonnet`).
  - **Voice**: Orchestrates Speech-to-Text (STT) parsing before the agent runs, and Text-to-Speech (TTS) audio generation as the agent streams its response.
- **Memory Management**:
  - **Short-term**: `langgraph` state (`MemorySaver` using PostgreSQL/Redis).
  - **Long-term**: Dedicated PostgreSQL tables storing user profiles, extracted preferences, and interaction summaries.
- **Human-in-the-Loop (HITL)**: Implemented natively in LangGraph using `interrupt` / breakpoints before critical nodes.

### 3.3 LLM Gateway (LiteLLM Proxy)
- **Deployment**: Standalone Docker container.
- **Purpose**: Standardize LLM calls, handle failovers (e.g., fallback from Claude 3.5 Sonnet to GPT-4o if rate-limited), and centralize API key management.
- **Performance**: Configured with a dedicated Redis instance for semantic caching and standard response caching.

### 3.4 Tools & Integrations (Official MCP SDK)
- **Standard**: Model Context Protocol (MCP) using the official `mcp` Python SDK.
- **Deployment**: Each tool suite (e.g., `xweb-mcp`, `pos-mcp`) is a separate server (using `mcp.server.fastapi.create_mcp_server`).
- **Interaction**: The LangGraph backend uses an MCP Client to discover and execute tools over **SSE (Server-Sent Events)** since the tools run on separate network services from the backend.
- **External Integration**: The MCP Tool Servers execute business logic by communicating with external application services (XWeb, POS, CRM, etc.) strictly via their standard **REST API** endpoints.

### 3.5 Knowledge Base & RAG (RAGFlow + PostgreSQL)
- **Service**: Standalone Open Source RAG engine (RAGFlow) handles document ingestion, chunking, and embedding.
- **Database**: Single PostgreSQL instance. RAGFlow and the core backend share this database, utilizing the `pgvector` extension for efficient similarity search.
- **Decoupling**: The backend queries RAGFlow via its REST API (or directly querying the vector tables if performance demands), keeping complex chunking logic out of the core agent.

### 3.6 Queue & Background Tasks (Celery + Redis)
- **Tasks**: Long-running non-blocking tasks (e.g., analyzing a completed conversation, updating a user's long-term profile, generating complex reports, triggering external workflows).
- **Broker/Result Backend**: Redis

---

## 4. Deep Dive: Key Technical Patterns

### 4.1 Multimodal Processing (Voice & Vision)
- **Vision Pipeline**: Images uploaded via the widget are handled via WebSocket or HTTP Multipart. They are temporarily stored or passed directly as base64 strings to LiteLLM, utilizing the natively integrated vision capabilities of models like `gpt-4o` or `claude-3-5-sonnet`.
- **Voice Pipeline (STT & TTS)**:
  - *Input (STT)*: Frontend uses `MediaRecorder` to send audio chunks via Socket.IO. Backend consumes chunks, calls a Speech-to-Text API (e.g., Whisper via LiteLLM), and feeds the resulting text into LangGraph.
  - *Output (TTS)*: As LangGraph streams text out, the backend batches text sentences to a TTS service (e.g., OpenAI TTS, ElevenLabs) and streams binary audio frames back to the frontend for immediate, low-latency playback.

### 4.2 LangGraph Human-in-the-Loop (HITL)
To implement financial action confirmation:
```python
from langgraph.graph import StateGraph, START, END
# ... state definition ...

# The tool node is marked as requiring approval
workflow.add_node("financial_tool", execute_financial_tool)
# Breakpoint before execution
workflow.compile(checkpointer=memory, interrupt_before=["financial_tool"])
```

### 4.2 LiteLLM config.yaml
Crucial for proxying to local models and handling failovers (both chat and embeddings):
```yaml
model_list:
  # Chat Model
  - model_name: lm-studio-model
    litellm_params:
      model: openai/local-model      # Name mappings for LM Studio
      api_base: http://host.docker.internal:1234/v1 # LM Studio default local port
      api_key: "lm-studio"
  - model_name: gemini-2.5-flash
    litellm_params:
      model: gemini/gemini-2.5-flash
      api_key: os.environ/GEMINI_API_KEY
  
  # Embedding Model
  - model_name: lm-studio-embedding
    litellm_params:
      model: openai/nomic-embed-text
      api_base: http://host.docker.internal:1234/v1
      api_key: "lm-studio"
  - model_name: lm-studio-embedding
    litellm_params:
      model: openai/text-embedding-3-small
      api_key: os.environ/OPENAI_API_KEY

router_settings:
  routing_strategy: usage-based-routing
  redis_host: redis
  redis_port: 6379
  cache_responses: true
```

### 4.3 Directory Structure (Annotated Logic)
```text
core_backend/                         # Main Backend Service (FastAPI + Socket.IO + LangGraph)
|-- app/
|   |-- __init__.py                   # FastAPI app factory & ASGI mount point
|   |-- main.py                       # Entrypoint: tao FastAPI instance, mount Socket.IO & routers
|   |
|   |-- api/                          # === API LAYER (Giao tiep voi Frontend) ===
|   |   |-- auth_routes.py            # REST endpoints: JWT Login, Register, Guest token generation
|   |   |-- socket_handler.py         # WebSocket hub: nhan message tu user, dieu phoi LangGraph,
|   |                                 #   stream token ve frontend, xu ly multimodal upload (image/audio)
|   |
|   |-- config/                       # === SYSTEM CONFIGURATION ===
|   |   |-- settings.py               # Pydantic BaseSettings: quan ly ENV (DB_URL, REDIS_URL, LITELLM_API_BASE,
|   |                                 #   LLM_MODEL, EMBEDDING_MODEL, JWT keys)
|   |
|   |-- memory/                       # === DATA PERSISTENCE & USER PROFILES ===
|   |   |-- long_term.py              # CRUD logic cho UserProfile table: luu ten, so thich, hanh vi.
|   |   |-- chat_history.py           # ChatHistoryTracker: logging tung doan chat tung le (chat_interactions) de phan tich, co tinh nang cho user vote rating (Good/Bad).
|   |-- multimodal/                   # === MEDIA ENGINE (Vision & Audio) ===
|   |   |-- processor.py              # Trung tam xu ly media: convert raw Base64/binary -> LangChain
|   |   |                             #   HumanMessage content blocks (image_url, input_audio).
|   |   |-- capabilities.py           # Model capability discovery: kiem tra LLM co ho tro Vision/Audio
|   |                                 #   hay khong, de quyet dinh pipeline xu ly phu hop.
|   |
|   |-- prompts/                      # === PROMPT ENGINEERING ===
|   |   |-- advisor.py                # Xay dung System Prompt phuc tap: inject RAG context, user profile,
|   |   |                             #   business rules, va persona instructions vao prompt.
|   |   |-- templates/                # Raw text templates cho cac loai prompt khac nhau
|   |       |-- system_prompt.txt     # Template System Prompt chinh cua Bot
|   |
|   |-- utils/                        # === SHARED TECHNICAL UTILITIES ===
|   |   |-- db.py                     # Database pool initializer & LangGraph PostgresSaver checkpointer.
|   |   |-- tokens.py                 # Utilities for token counting and estimation (LLM Context limit).
|   |   |-- logger.py                 # Structured logging: format chuan cho debug (timestamp, module, level).
|   |   |-- pii_mask.py               # Security: Regex scrub so dien thoai, email, password truoc khi gui data.
|   |-- workflows/                    # === LANGGRAPH BRAIN (Core AI Architecture) ===
|       |-- state.py                  # GraphState TypedDict: dinh nghia schema chung cho tat ca node
|       |                             #   (messages, session_id, user_id, rag_documents, thinking, metadata)
|       |-- graph.py                  # StateGraph compiler: lap ghep cac node thanh cyclic graph,
|       |                             #   cau hinh checkpointer (PostgresSaver) cho Short-Term Memory,
|       |                             #   va compile thanh runnable graph.
|       |-- hitl.py                   # Human-In-The-Loop: gui thong bao Telegram khi can manager phe duyet,
|       |                             #   cung cap REST webhook `/api/v1/hitl/approve/{id}` de resume graph.
|       |
|       |-- nodes/                    # === ISOLATED PROCESSING NODES (Tung "ky nang" cua Bot) ===
|           |-- generate.py           # CORE NODE: Goi LiteLLM API, xu ly guard fallback, emit Socket.IO
|           |                         #   events (message_stream, message_complete). Day la node chinh
|           |                         #   tao ra cau tra loi cho nguoi dung.
|           |-- guard.py              # SECURITY NODE: Kiem tra message co phai spam/off-topic khong.
|           |                         #   Scan TOAN BO lich su hoi thoai de phat hien multimodal context.
|           |                         #   Neu bypass -> tra ve fallback message ngay lap tuc.
|           |-- rag_search.py         # RAG NODE: Thuc hien vector similarity search trong PostgreSQL
|           |                         #   (pgvector). Inject ket qua tim kiem vao GraphState.rag_documents
|           |                         #   de LLM co them context khi tra loi.
|           |-- tools.py              # TOOL NODE: Thuc thi cac function nhu get_time, get_weather.
│   │       ├── nodes/            # Isolated Logic Units (Processing Nodes)
│   │           ├── generate.py   # Core Generation: delegates to LiteLLM & handles fallbacks
│   │           ├── guard.py      # Security/Hallucination Guard: blocks unrelated text queries
│   │           ├── rag_search.py # RAG Logic: performs native vector search in PostgreSQL (pgvector)
│   │           ├── tools.py      # Tool Executor: thuc thi cac lenh nhu update_user_profile
│   │           ├── tool_defs.py  # Definitions: JSON schemas cho LiteLLM's function calling
│   │           ├── stream_handler.py # Parser: Real-time XML/Thinking tag parsing for WebSockets
│   │           ├── fetch_profile.py  # Profile Ingestion: nạp dữ liệu User từ DB vào State
│   │           └── profile_analyzer.py # Deprecated/Batch: Dung cho phan tich chuyen sau hang loat
|
|-- scripts/                          # === UTILITY & DEVOPS SCRIPTS ===
|   |-- seed.py                       # Pre-seed DB voi mock data (UserProfiles, RAG vectors) de test
|   |-- verify_multimodal_memory.py   # Automated test: kiem tra multimodal context awareness & guard
|
|-- tests/                            # === BACKEND TEST SUITE (Pytest) ===
|   |-- unit/                         # Function-level isolated testing (mock dependencies)
|   |-- scenarios/                    # Integration tests: PII masking, token loops, DB locks, Socket.IO
|       |-- test_socket_io.py         # Test Socket.IO connection, message handling, Redis locks
|
|-- Dockerfile                        # Container packaging cho core_backend service
|-- requirements.txt                  # Python dependencies (langchain, litellm, socketio, fastapi...)
```

### 4.4 Advanced Memory & Personalization Strategy
To provide deeply personalized answers for authenticated users, memory is heavily segregated:

**1. Short-Term Memory (Session Context)**
- Managed natively by LangGraph's `PostgresSaver` checkpointer (configured in `utils/db.py`).
- Tied directly to a specific `thread_id` (a single chat session).
- Responsible for exactly "what were we just talking about 5 minutes ago?".

**2. Long-Term Memory (User Profile & Behavior)**
- Managed via `memory/long_term.py` with custom PostgreSQL tables.
- **Data Categories**:
  - *Static Profile*: Name, Job Title, Company, verified email.
  - *Dynamic Preferences*: Extracted continuously from chats (e.g., "User prefers short technical answers").
  - *Behavioral Logs*: Purchase history, features interacted with.
- **Flow Integration**: 
  - *Ingestion*: `nodes/fetch_profile.py` tải Profile vào GraphState khi bắt đầu turn.
  - *Explicit Update (Reactive)*: Agent sử dụng tool `update_user_profile` để cập nhật ngay lập tức khi phát hiện người dùng cung cấp thông tin mới (Tên, sở thích, sự thật). Cách này tối ưu hơn việc quét lại toàn bộ sau mỗi turn.
  - *Background Extraction (Optional)*: `nodes/profile_analyzer.py` có thể được gọi định kỳ để phân tích hành vi tinh tế.

### 4.5 Detailed Module Responsibilities
The folder structure ensures the code is highly maintainable:
- **`workflows/state.py`**: Định nghĩa schema dữ liệu (`TypedDict`) duy nhất chạy xuyên suốt các node.
- **`workflows/graph.py`**: Rút gọn quy trình, loại bỏ việc cưỡng bức phân tích profile sau mỗi tin nhắn để giảm latency.
- **`workflows/nodes/tools.py`**: Tích hợp logic xử lý DB trực tiếp cho các tool cập nhật Profile, giúp AI phản hồi "Tôi đã ghi nhớ tên bạn" một cách tự nhiên.
- **`workflows/nodes/`**: Moi file la mot "ky nang" rieng biet cua Bot. Vi du: `rag_search.py` chi lo tim du lieu, `generate.py` chi lo goi AI. Viec tach nho nay giup ban debug cuc nhanh khi co loi o mot khau cu the.
- **`multimodal/processor.py`**: Don vi xu ly trung tam cho hinh anh va am thanh. No tu dong chuan hoa cac dau vao hon hop (Text + Image + Voice) ve dinh dang ma Gemini/GPT hieu duoc.
- **`api/socket_handler.py`**: Cua ngo giao tiep thoi gian thuc. No chiu trach nhiem nhan tin nhan tu nguoi dung, quan ly session lock (tranh spam) va dieu phoi viec stream ket qua tu AI ve cho Web Widget.
- **`utils/pii_mask.py`**: Lop bao mat quan trong, tu dong quet va che cac thong tin nhay cam (SDT, Email, Password) truoc khi gui du lieu len Cloud LLM.
- **`memory/long_term.py`**: Chua cac cau lenh SQL toi uu de luu tru va truy van "ky uc dai han" cua khach hang, giup Bot cang chat cang thong minh.
- **`workflows/nodes/stream_handler.py`**: Bo phan tich (parser) luong du lieu. No boc tach phan "Deep Thinking" cua AI (nam trong the `<thinking>`) de hien thi rieng tren giao dien, tao cam giac Bot dang thuc su suy nghi.

### 4.6 Streaming & Thought Process UI (Agentic Reasoning)
To achieve an advanced UI where the AI's internal reasoning (e.g., "Thought for 5s") is separated from the final response, the streaming architecture is heavily customized:
1. **Prompt Injection**: System prompts instruct the LLM to wrap all its internal reasoning, tool selection logic, and scratchpad thoughts inside `<thinking> ... </thinking>` XML tags before yielding the final user-facing response.
2. **Backend Streaming Parser (`api/socket_handler.py`)**:
   - As tokens stream from LiteLLM/LangGraph, the WebSocket handler parses the stream in real-time.
   - It identifies when the `<thinking>` tag opens and routes those specific tokens to a `thought_stream` WebSocket event.
   - Once the `</thinking>` tag closes, it routes subsequent tokens to the standard `message_stream` event.
3. **Frontend Rendering**:
   - The Preact widget maintains two distinct state variables during a stream: `currentThought` and `currentResponse`.
   - The UI natively supports rendering the `thought_stream` inside an expandable accordion component (similar to the provided screenshots).
   - This keeps the final response clean while allowing advanced users to inspect the agent's logic.

### 4.7 Docker Compose Snippet
```yaml
services:
  postgres:
    image: pgvector/pgvector:pg16
    ports:
      - "5432:5432"
    environment:
      POSTGRES_USER: ${POSTGRES_USER:-admin}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:-admin}
      POSTGRES_DB: ${POSTGRES_DB:-smartsales}
    volumes:
      - pgdata:/var/lib/postgresql/data
    profiles: [ "infra", "backend" ]

  redis:
    image: redis:alpine
    ports:
      - "6379:6379"
    profiles: [ "infra", "backend" ]

  litellm_proxy:
    image: ghcr.io/berriai/litellm:main-latest
    ports:
      - "4000:4000"
    volumes:
      - ./litellm_config.yaml:/app/config.yaml
    environment:
      - OPENAI_API_KEY=${OPENAI_API_KEY}
      - GEMINI_API_KEY=${MY_GEMINI_KEY}
      - LITELLM_MASTER_KEY=${LITELLM_MASTER_KEY:-sk-litellm-proxy}
      - DATABASE_URL=postgresql://${POSTGRES_USER:-admin}:${POSTGRES_PASSWORD:-admin}@postgres:5432/${POSTGRES_DB:-smartsales}
    command: [ "--config", "/app/config.yaml" ]
    depends_on:
      - redis
      - postgres
    profiles: [ "infra", "backend" ]

  core_backend:
    build: ./core_backend
    ports:
      - "8000:8000"
    env_file: .env
    environment:
      - DATABASE_URL=postgresql://${POSTGRES_USER:-admin}:${POSTGRES_PASSWORD:-admin}@postgres:5432/${POSTGRES_DB:-smartsales}
      - REDIS_URL=redis://redis:6379/0
      - LITELLM_API_BASE=${LITELLM_API_BASE}
      - LITELLM_API_KEY=${LITELLM_API_KEY:-sk-litellm-proxy}
      - LLM_MODEL=${LLM_MODEL:-lm-studio-model}
      - MCP_SERVER_URL=${MCP_SERVER_URL}
      ...
    depends_on:
      - postgres
      - redis
      - litellm_proxy
    profiles: [ "backend" ]

  mcp_server:
    build: ./mcp_servers
    ports:
      - "8001:8001"
    env_file: .env
    environment:
      - MCP_INTERNAL_API_KEY=${MCP_INTERNAL_API_KEY}
    profiles: [ "tools", "backend" ]

volumes:
  pgdata:
```
