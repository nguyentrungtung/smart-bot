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
  - model_name: lm-studio-model
    litellm_params:
      model: openai/gpt-4o
      api_key: os.environ/OPENAI_API_KEY
  
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

### 4.3 Directory Structure
```text
smart-bot/
├── .env                  # Global environment variables
├── docker-compose.yml    # Main orchestration
├── core_backend/                 # Python, LangGraph, Socket.IO
│   ├── app/
│   │   ├── config/               # Global config (litellm urls, redis, db)
│   │   ├── api/                  # REST API & WebSocket endpoints
│   │   ├── mcp_clients/          # SSE clients communicating with MCP servers
│   │   ├── prompts/              # Centralized System Prompt Management
│   │   │   ├── index.py          # Prompt builder functions
│   │   │   └── templates/        # .txt or structured config files
│   │   ├── utils/                # Common utility functions
│   │   │   ├── logger.py         # Custom structured logging
│   │   │   └── helpers.py        # Generic text parsers, date formatting, etc
│   │   ├── middleware/           # Request/Response interceptors
│   │   │   ├── pii_scrubber.py   # Regex to mask sensitive data (PII, Passwords)
│   │   │   ├── auth.py           # JWT token validation (RS256 Public Key) & session locking
│   │   │   └── format.py         # Response payload normalization
│   │   ├── schemas/              # Data validation and strict rule definitions
│   │   │   ├── rules.yaml        # Business rules (e.g. Confidence > 0.7, max 3 images)
│   │   │   └── validators.py     # Pydantic models, strict MIME type & file size checks
│   │   ├── multimodal/           # Media Processing pipelines
│   │   │   ├── vision.py         # Image -> Base64 parsing for LLMs
│   │   │   └── audio.py          # STT (Whisper) & TTS processing loops
│   │   ├── memory/               # Memory Layer
│   │   │   ├── short_term.py     # Session thread state (Thread IDs)
│   │   │   └── long_term.py      # Profile DB (preferences, behavior, name)
│   │   └── workflows/            # LangGraph Flows & State
│   │       ├── state.py          # Defined GraphState schema
│   │       ├── nodes/            # Isolated node execution functions
│   │       │   ├── rag_search.py # Native backend logic to query pgvector (Not MCP)
│   │       │   └── ...           # Other nodes (generate, route, etc)
│   │       ├── hitl.py           # Human-In-The-Loop confirmation handlers
│   │       └── graph.py          # Compile the main StateGraph
│   ├── migrations/               # Alembic database schema migrations
│   │   ├── versions/             # Auto-generated SQL version scripts
│   │   └── env.py                # Alembic environment config
│   ├── scripts/                  # Utility execution scripts
│   │   ├── seed.py               # Pre-populates DB with mock UserProfiles & RAG vectors for testing
│   │   └── run_clean_tests.py    # Master script to automate Docker teardown, rebuild, and pytest
│   ├── tests/                    # Automated Test Suites
│   │   ├── unit/                 # Mocked function testing
│   │   └── scenarios/            # Integration logic for edge cases (PII, RAG, File limits)
│   ├── alembic.ini               # Alembic CLI config
│   ├── Dockerfile
│   └── requirements.txt
├── mcp_servers/          # Independent Tool Servers
│   ├── basic_tools/      # Simple utility server (Time, Weather via open-meteo)
│   ├── xweb_manager/     # MCP server for website creation
│   └── pos_integration/  # MCP server for order checking
├── frontend_widget/      # Preact/Vanilla JS embeddable script
│   ├── src/
│   │   ├── bootloader.js # Injects iframe
│   │   └── iframe_app/   # Actual chat UI
│   └── package.json
└── ragflow_config/       # Configs for standalone RAG service
```

### 4.4 Advanced Memory & Personalization Strategy
To provide deeply personalized answers for authenticated users, memory is heavily segregated:

**1. Short-Term Memory (Session Context)**
- Managed natively by LangGraph's built-in `MemorySaver` (using Postgres or Redis).
- Tied directly to a specific `thread_id` (a single chat session).
- Responsible for exactly "what were we just talking about 5 minutes ago?".

**2. Long-Term Memory (User Profile & Behavior)**
- Managed as custom PostgreSQL tables queried independently of the core LangChain message history.
- **Data Categories**:
  - *Static Profile*: Name, Job Title, Company, verified email.
  - *Dynamic Preferences*: Extracted continuously from chats (e.g., "User prefers short technical answers", "User is interested in the CRM product").
  - *Behavioral Logs*: Purchase history, features interacted with.
- **Flow Integration**: When a user connects, their Long-Term Profile is fetched and injected into the LangGraph `State` as system context *before* the LLM generates a response. A background Celery task analyzes completed chat sessions to extract new facts and update this Long-Term Profile asynchronously.

### 4.5 Development Workflow (LangGraph Modularity)
The folder structure (`workflows/`) ensures the code is highly maintainable:
- **`state.py`**: Defines the precise schema (Pydantic models / `TypedDict`) that flows between nodes.
- **`prompts/`**: A centralized location to manage all LLM system prompts, ensuring the persona and instructions remain consistent across the application rather than hardcoded in individual files.
- **`nodes/rag_search.py`**: RAG is a core pipeline feature, not an external tool. The graph natively executes a node that performs vector similarity search against the PostgreSQL (`pgvector`) database using LangChain's vectorstore integrations, injecting the retrieved context directly into the graph state.
- **`nodes/` (General)**: Each node (e.g., `analyze_intent`, `execute_tool`, `generate_response`) is a separate file that strictly reads from, and returns updates to, the State.
- **`workflows/`**: The true "brain" of the agent. Splitting the State from the Graph logic prevents circular import errors, while `nodes/` isolates chunked execution tasks (like generating vs fetching RAG).
- **`hitl.py`**: Contains the logic for intercepting state at breakpoints and waiting for human manager UI approvals.
- **`config/`**: Centralizes environment variables, easily allowing swapping between staging/prod databases or LLM endpoints.
- **`middleware/`**: Protects the core system. Contains interceptors that run *before* requests hit the AI (e.g., `auth.py` for decoding JWT via RS256 Public Key and checking session locks, `pii_scrubber.py` to redact passwords/phone numbers via regex to protect enterprise data) and *after* for payload formatting.
- **`schemas/`**: Houses Pydantic models and validation rules. It strictly blocks illegal file uploads (e.g., rejecting PDFs/Executables, limiting images to 5MB) and defines business rules (e.g., RAG Confidence Threshold must be `> 0.7`).
- **`utils/`**: Holds common, cross-node modules like standardized logging formats, heavy string-manipulation helpers, or shared data-format converters so that node files remain strictly about business logic.
- **`multimodal/`**: Contains the decoupled logic `vision.py` and `audio.py` for dealing specifically with file I/O streams and connecting to the Whisper/TTS APIs, keeping the core LangGraph nodes free of massive image base64 processing blocks.

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
version: '3.8'
services:
  postgres:
    image: pgvector/pgvector:pg16
    environment:
      POSTGRES_USER: smartuser
      POSTGRES_PASSWORD: password
      POSTGRES_DB: smartbotdb
    volumes:
      - pgdata:/var/lib/postgresql/data

  redis:
    image: redis:alpine
    ports:
      - "6379:6379"

  litellm_proxy:
    image: ghcr.io/berriai/litellm:main-latest
    volumes:
      - ./litellm_config.yaml:/app/config.yaml
    environment:
      - OPENAI_API_KEY=${OPENAI_API_KEY}
      - LITELLM_MASTER_KEY=${LITELLM_MASTER_KEY}
    command: [ "--config", "/app/config.yaml", "--detailed_debug" ]

  core_backend:
    build: ./core_backend
    environment:
      - DATABASE_URL=postgresql://${POSTGRES_USER}:${POSTGRES_PASSWORD}@postgres:5432/${POSTGRES_DB}
      - REDIS_URL=redis://redis:6379/0
      - LITELLM_URL=${LITELLM_API_BASE}
      - LITELLM_API_KEY=${LITELLM_API_KEY}
      - LLM_MODEL=${LLM_MODEL}
      - EMBEDDING_MODEL=${EMBEDDING_MODEL}
    depends_on:
      - postgres
      - redis
      - litellm_proxy

  mcp_basic_tools:
    build: ./mcp_servers/basic_tools
    ports:
      - "8001:8001"

volumes:
  pgdata:
```
