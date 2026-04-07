# 🤖 Smart-Bot Master AI Instructions (AGENTS.md)

## 📌 Project Overview
- **Name:** Smart-Bot MVP
- **Goal:** Enterprise-grade AI advisor and internal action-executor (multimodal, iframe widget, RAG, custom MCP tools).
- **Tech Stack:** Preact (Widget), Python 3.11+, LangGraph, LiteLLM (Gemini 2.5-flash / LM Studio), FastAPI/Socket.io, RAGFlow, PostgreSQL (pgvector), Redis.
- **Current Phase:** Building MVP.

## 🧠 Core Objectives & Arch (from Research)
1. **Intelligent Advising**: Provide accurate product information for enterprise solutions.
2. **Action Execution**: Execute agentic workflows (e.g., website creation, data retrieval).
3. **Multimodal**: Support Voice (STT/TTS) and Vision (Image parsing) natively.
4. **Hybrid Memory**: Short-term session via LangGraph Checkpointer + Long-term User Profiles in Postgres.
5. **Decoupled Architecture**: 
   - Frontend Agent UI (Iframe Widget)
   - Core LangGraph Backend (FastAPI + Socket.io)
   - LLM Gateway (LiteLLM Proxy)
   - MCP Server (Tools/Integrations)
   - Knowledge Base (RAGFlow/Posgres Vector)

## 🧠 How You (The AI) Should Think
1. **UNDERSTAND FIRST:** NEVER start generating code before you have read the `docs/TechDesign-Smart-Bot-MVP.md` and `docs/PRD-Smart-Bot-MVP.md`.
2. **CHECK PATTERNS:** Before implementing new architecture, consult `agent_docs/code_patterns.md`. 
3. **HYBRID MEMORY:** Always check if information should be stored in Short-Term (LangGraph State) or Long-Term (User Profile via `update_user_profile` tool).
4. **RESILIENCE:** All external MCP calls MUST go through the `app.connectors.mcp.client.call_mcp_tool` which uses a Circuit Breaker.

## 📁 Directory Structure (Annotated Logic)
```text
core_backend/                         # Backend Service (FastAPI + LangGraph)
|-- alembic/                          # DB migrations for PostgreSQL
|-- app/                              # Main application package
|   |-- main.py                       # FastAPI & Socket.IO Entrypoint
|   |-- api/                          # Interface layer
|   |   |-- auth_routes.py            # JWT-based REST authentication
|   |   |-- chat_routes.py            # Session management & History cleanup
|   |   |-- socket_handler.py         # Socket.IO logic for real-time chat & streaming
|   |-- config/                       # Application configuration
|   |   |-- settings.py               # Pydantic settings loading from .env
|   |-- connectors/                   # External service integrations
|   |   |-- mcp/                      # Model Context Protocol (MCP) clients
|   |   |   |-- client.py             # Resilience MCP client with Circuit Breaker
|   |   |-- local_tools.py            # Direct Python tools (DB, File, System tasks)
|   |-- memory/                       # State persistence
|   |   |-- chat_history.py           # Session-based chat logs & feedback storage
|   |   |-- long_term.py              # Persistent User Profile management
|   |-- middleware/                   # Request/Response processing
|   |   |-- auth.py                   # Token validation & Blacklisting (Redis)
|   |   |-- pii_scrubber.py           # PII detection and masking
|   |-- multimodal/                   # Vision/Voice processing
|   |   |-- audio_pipeline.py         # Server-side STT: FFmpeg → faster-whisper (Vietnamese)
|   |   |-- capabilities.py           # Multimodal feature flags & detection
|   |   |-- processor.py              # Base64 media processing for LLMs (Vision + STT)
|   |-- prompts/                      # LLM Persona & Prompting
|   |   |-- templates/                # Reusable prompt definitions
|   |   |   |-- advisor.py            # Primary Sales Advisor persona
|   |-- schemas/                      # Data models (Pydantic)
|   |   |-- socket_io.py              # Real-time event communication models
|   |-- utils/                        # Shared helper functions
|   |   |-- db.py                     # SQLAlchemy engine and session logic
|   |   |-- logger.py                 # Centralized structured logging
|   |   |-- redis.py                  # Redis client for caching/blacklisting
|   |   |-- resilience.py             # Circuit Breaker & Retry decorators
|   |   |-- tokens.py                 # Context window & Token management utilities
|   |-- workflows/                    # LangGraph Cognitive Brain
|       |-- graph.py                  # Workflow compilation & Node routing
|       |-- state.py                  # Universal GraphState definition
|       |-- hitl.py                   # Human-In-The-Loop (HITL) interception
|       |-- nodes/                    # Atomic functional steps
|           |-- fetch_profile.py      # User profile retrieval
|           |-- generate.py           # Main LLM generation (LiteLLM)
|           |-- guard.py              # Input/Output safety filtering
|           |-- message_converter.py  # Message format harmonization
|           |-- profile_analyzer.py   # User intent & interest extraction
|           |-- rag_search.py         # Knowledge base retrieval (RAGFlow/Posgres)
|           |-- stream_handler.py     # Token-by-token streaming logic + tool-call token stripping
|           |-- summarizer.py         # Context compression & memory management
|           |-- tool_defs.py          # Dynamic tool schema generation
|           |-- tools.py              # Unified tool execution engine
|           |-- vision_scrubber.py    # Multimodal cleanup (replace images with text descriptions)
|-- scripts/                          # DevOps & Maintenance tools
|   |-- seed_db.py                    # Seeds DB with Admin & RAG data
|   |-- clear_memory.py               # Maintenance: Truncate Short/Long term memory (e.g. `python scripts/clear_memory.py --short-term` to clear LangGraph checkpoints, blobs, and writes)
|   |-- test_12turn_scenario.py       # E2E test: 12-turn conversation with tool calls, RAG, profile memory, session isolation (17/17 PASS)
|   |-- test_voice_chat.py            # E2E test: 7-turn Vietnamese voice chat with 4 voice + 3 text turns (7/7 PASS)
|-- tests/                            # Pytest test suite
|-- alembic.ini                       # Migration config
|-- Dockerfile                        # Backend container recipe
|-- requirements.txt                  # Python dependency manifest
```

## 🐋 Docker Compose Snippet (Current)
```yaml
services:
  postgres:
    image: pgvector/pgvector:pg16
    ports: ["5432:5432"]
    profiles: ["infra", "backend"]

  redis:
    image: redis:alpine
    command: redis-server --requirepass ${REDIS_PASSWORD}
    ports: ["6379:6379"]
    profiles: ["infra", "backend"]

  litellm_proxy:
    image: ghcr.io/berriai/litellm:main-latest
    ports: ["4000:4000"]
    extra_hosts: ["host.docker.internal:host-gateway"]
    environment:
      - LOCAL_MODEL_API_BASE=${LOCAL_MODEL_API_BASE:-http://host.docker.internal:1234/v1}
      - REDIS_PASSWORD=${REDIS_PASSWORD}
    profiles: ["infra", "backend"]

  core_backend:
    build: ./core_backend
    ports: ["8000:8000"]
    env_file: .env
    profiles: ["backend"]

  mcp_server:
    build: ./mcp_servers
    ports: ["8001:8001"]
    profiles: ["tools", "backend"]
```

## 🚫 What NOT To Do (Strict Anti-Patterns)
1. **NO** Linux/Bash: Host is Windows 11 PowerShell.
2. **NO** `HS256`: Strictly use **RS256** RSA Keypairs for JWT.
3. **NO** Unauthenticated Redis: Always use `REDIS_PASSWORD`.
4. **NO** Vector Dimensions != 768: Standardize to **768** for Local/Cloud sync.
5. **NO** Implicit DB Commits: Always use `async with conn.transaction()` in DB tools.
6. **NO** Plain Redis Blacklist: Always set TTL on blacklisted tokens.
7. **NO** Unified MCP hardcoding: Use the `mcp.client` wrapper for resilience.
8. **NO** Skipping Local Tools: Simple tasks (Time, File) must be in `local_tools.py`, NOT MCP.
9. **NO** Context Overflow: Always respect `MAX_HISTORY_TOKENS` and use `summarizer.py`.
12. **NO** Single Transaction for Checkpoint Deletes: LangGraph Postgres Checkpointer uses `checkpoints`, `checkpoint_writes`, and `checkpoint_blobs`. Always use separate connection/transaction blocks per table when deleting to avoid Foreign Key locking and aborted transactions.
13. **NO** Client-side Session Logic: Strictly use the `/new-session` API to initialize `session_id`; NEVER generate random IDs in the Frontend.
14. **NO** Plain-text Passwords: Password hashing MUST use `passlib` with `bcrypt`.
15. **NO** Guest Login: Authentication must always verify `user_id` and `password` against the `users` table; no unauthenticated token generation is allowed.
16. **NO** Missing Embeddings: The `documents` table MUST contain both `content` and `embedding` (Vector 768) columns for RAG.
17. **NO** Red Dot Ignored: The UI includes a Status Dot (Green: Connected, Red: Auth Error). If it turns red, the AI should advise the user to authenticate.

## 📁 Updated UI/UX Patterns
- **Status Dot**: Header-level indicator for real-time authentication status.
- **Auto-Refresh**: Socket sessions automatically attempt token refresh on expiry.
- **Partner Handshake**: Website integration uses `postMessage` with `SMART_BOT_AUTH` type to securely inject guest tokens from partner backends.

