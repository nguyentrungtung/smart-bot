# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Prime Directives

1. **READ AGENTS.md FIRST** — it is the master rulebook for file structure, patterns, and anti-patterns.
2. **READ THE TECH DESIGN** before creating any new Python or JS logic files: `docs/TechDesign-Smart-Bot-MVP.md`.
3. **FILE CREATION** — create modular files exactly as defined in the `AGENTS.md` directory structure block.
4. **SHELL ENVIRONMENT** — this is Windows 11 with bash via Git Bash/Claude Code. Use Unix-style paths (`/`) in shell commands. Prefer `docker compose exec` over running Python directly.

---

## Running the Stack

### First-time setup
```bash
# Generate RS256 JWT keypair
python scripts/generate_jwt_keys.py

# Start infra first, then full stack
docker compose --profile infra up -d
docker compose --profile backend --profile tools up -d --build

# Apply DB migrations and seed data
docker compose exec core_backend alembic upgrade head
docker compose exec core_backend python scripts/seed_db.py
```

### Day-to-day
```bash
# Rebuild only the backend after code changes
docker compose up -d --build core_backend

# Tail backend logs
docker compose logs -f core_backend

# Frontend dev server (hot reload)
cd frontend/widget && npm install && npm run dev
```

### Running tests
```bash
# Full test suite (inside container)
docker compose exec core_backend python scripts/run_tests.py

# Run pytest directly for a single test file
docker compose exec core_backend pytest tests/integration/test_auth.py -v

# Specific validation scripts
docker compose exec core_backend python scripts/test_e2e_socket_flow.py
docker compose exec core_backend python scripts/test_multimodal_vision_voice.py
docker compose exec core_backend python scripts/test_bypass_logic.py

# Voice/Audio Chat Test (7-turn Vietnamese conversation with 4 voice turns)
docker compose exec core_backend python scripts/test_voice_chat.py

# 12-turn E2E Scenario Test (with tool calls, RAG, profile memory, session isolation)
docker compose exec core_backend python scripts/test_12turn_scenario.py
```

### Voice Testing Utilities

**test_voice_chat.py** — Full audio pipeline E2E test
- Generates synthetic WAV audio (numpy sine wave, 16kHz, 1.5s duration)
- Encodes as base64, sends via Socket.IO with multimodal payload
- Verifies STT pipeline: [DECODE] → [CONVERT] → [PARSE] → [TRANSCRIBE]
- Tests 7 turns: 4 voice + 3 text, mixing Vietnamese language  
- Validates: profile seeding (name=Minh), memory recall, tool calls, RAG search
- Assertions: keyword matching, response latency tracking, session lock health
- **Run time**: ~2 min (LM Studio local model); timeouts: `TURN_TIMEOUT=240s`, `BETWEEN_TURNS=5s`

**Backend logs** — Check audio pipeline execution
```bash
docker compose logs core_backend 2>&1 | grep -E 'AUDIO|DECODE|CONVERT|PARSE|TRANSCRIBE|STT'
```

### Maintenance
```bash
# Clear memory stores (use --all, --short-term, --long-term, or --analytics)
docker compose exec core_backend python scripts/clear_memory.py --all

# Re-initialize LangGraph checkpointer manually
docker compose exec core_backend python scripts/setup_checkpointer.py
```

---

## Architecture Overview

### Request Flow
```
Parent Page (postMessage JWT)
  → Preact Widget (iframe, Socket.IO client)
    → FastAPI + Socket.IO (core_backend :8000)
      → LangGraph Workflow (graph.py)
          ├── guard node (safety filter)
          ├── fetch_profile node (long-term memory)
          ├── rag_search node (pgvector cosine similarity, 0.7 threshold)
          ├── summarizer node (fires when tokens > SUMMARY_THRESHOLD=1500)
          ├── tools node (via MCP client or local_tools.py)
          └── generate node (LiteLLM proxy :4000 → LM Studio → Gemini → GPT-4o)
```

### Key Boundaries
- **MCP vs Local tools**: Time, filesystem, and direct DB writes → `app/connectors/local_tools.py`. All external integrations → MCP server (`mcp_servers/`, port 8001) called via `app.connectors.mcp.client.call_mcp_tool` (Circuit Breaker enforced).
- **LLM access**: Never call LiteLLM or model APIs directly from nodes — always go through the proxy at `LITELLM_API_BASE` (port 4000). Fallback chain: local LM Studio → Gemini 2.5 Flash → GPT-4o.
- **Embeddings**: All vectors MUST be 768 dimensions. This is a hard constraint for local↔cloud sync compatibility.
- **RAG fallback**: If cosine similarity < 0.7, respond with the configured Vietnamese fallback message — do not hallucinate.

### Auth Model
- RS256 JWT (keypair in `.keys/`). HS256 is strictly forbidden.
- Access token validated + blacklist-checked in `app/middleware/auth.py` via Redis on every request.
- Widget authenticates via `exchange-token` endpoint using a short-lived token passed from the parent page over `postMessage`.

### Memory Model
- **Short-term**: LangGraph `AsyncPostgresSaver` checkpoints per session (`checkpoints` / `checkpoint_writes` / `checkpoint_blobs` tables). Context window capped at `MAX_HISTORY_TOKENS=3000`; summarizer fires at `SUMMARY_THRESHOLD=1500`.
- **Long-term**: `user_profiles` table. Extracted by `profile_analyzer` node after each conversation turn.

### Multimodal — Vision & Voice

**Vision Pipeline** (Image Analysis)
- Controlled by `MULTIMODAL_ENABLED` env flag; routes to Gemini (base64 encoding in `multimodal/processor.py`)
- Images converted to `image_url` blocks (data URI format) for OpenAI/Gemini compatibility
- `vision_scrubber.py` node replaces image blocks with text descriptions after generation to save tokens in future turns

**Voice/Audio Pipeline** (Server-Side STT — Community Standard)
- Browser captures audio (webm/ogg/mp4) → base64 encode → Socket.IO
- Backend processes in `app/multimodal/audio_pipeline.py`:
  1. **DECODE**: base64 → raw audio bytes
  2. **CONVERT**: FFmpeg pipe (any format → 16kHz mono PCM s16le) — zero temp files, memory-only
  3. **PARSE**: numpy `frombuffer` (bytes → float32 array [-1.0, 1.0])
  4. **TRANSCRIBE**: faster-whisper (SYSTRAN, 21.9k⭐) Vietnamese STT with VAD filter
- Model runs in thread executor (CPU-bound); lazy-loads on first call (~10s), then cached
- Language confidence < 0.5 → rejected (prevents hallucination on noise/silence)
- Transcription injected as: `[Giọng nói của người dùng]: {text}` text block → LLM
- **Why STT-first (not native audio)?** Model-agnostic (LM Studio, Gemini, OpenAI all receive text), transcription is auditable, avoids input_audio format fragmentation between providers

### HITL (Human-in-the-Loop)
- Sensitive tool calls trigger a Telegram approval workflow (`workflows/hitl.py`).
- Approval tracked by UUID; backend polls Redis until approved or timeout.

### Frontend Widget
- Preact SPA, bundled by Vite, embedded via `bootloader.js` as an iframe.
- Communicates with parent via `postMessage` for JWT injection and iframe resize events.
- Status Dot: green = connected + authenticated, red = auth error.
- Supports full-screen toggle and manual resize handle (top-left corner).

### Docker Services

| Service | Port | Profile |
|---|---|---|
| `postgres` (pgvector) | 5432 | infra, backend |
| `redis` | 6379 | infra, backend |
| `litellm_proxy` | 4000 | infra, backend |
| `core_backend` | 8000 | backend |
| `mcp_server` | 8001 | tools, backend |

---

## Known Issues & Bug Fixes (Voice Testing Session)

This section documents critical bugs discovered during voice/audio testing (Session 3) and their fixes. Future AI agents should be aware of these patterns to avoid regression.

### Fixed Bugs

1. **[generate.py] Double `message_complete` Emit**
   - **Issue**: Guard bypass and error paths in `generate_response` emitted `message_complete`, but `socket_handler` also emitted it after the agent node → late duplicate event bled into next turn → T2 response event set prematurely
   - **Root Cause**: Missing coordination between node-level and socket-level event emission
   - **Fix**: Removed redundant `message_complete` emits from `generate.py` lines 54 and 184. Let `socket_handler` alone emit `message_complete` for all agent node completions
   - **Test**: `test_voice_chat.py` T1 waited exactly 30s before succeeding (no more bleed into T2)

2. **[main.py] Whisper Model Pre-Warm Import Bug**
   - **Issue**: `_prewarm_whisper()` imported `_get_whisper_model` from `app.multimodal.processor` but function lives in `app.multimodal.audio_pipeline`
   - **Impact**: First audio message took 30s+ to process (model loaded cold instead of pre-warmed at startup)
   - **Fix**: Changed import path to `audio_pipeline`
   - **Verification**: Backend logs now show `✅ faster-whisper model pre-warmed and ready.`

3. **[stream_handler.py] Local Model Tool-Call Token Leak**
   - **Issue**: LM Studio outputs raw tool-call tokens like `<|tool_call>call:get_current_time{}<tool_call|>` even without tools provided; stream handler's `fullmatch()` only caught tokens in complete chunks, but streaming arrives fragmented
   - **Root Cause**: Using `_TOOL_LEAK_PATTERN.fullmatch(safe.strip())` which requires entire chunk to be a token; partial tokens never matched
   - **Fix**: Changed to `_TOOL_LEAK_PATTERN.sub("", safe).strip()` to strip embedded tokens from any chunk
   - **Test**: T3 response no longer contains `<|tool_call>...` tokens

4. **[advisor.py] Hallucinating Non-Existent `search_knowledge_base` Tool**
   - **Issue**: System prompt explicitly told LLM to call `search_knowledge_base` (lines 15, 44), but tool doesn't exist — RAG is automatic via graph node
   - **Impact**: LLM repeatedly tried to call non-existent tool → `SECURITY: Rejected unknown tool` errors in every turn
   - **Fix**: Removed all `search_knowledge_base` references; updated prompt to point LLM to injected RAG context instead
   - **Result**: No more security rejections; LLM focuses on available tools (get_current_time, get_weather, update_user_profile)

5. **[test_voice_chat.py] Stream Event Key Mismatch**
   - **Issue**: Test's `_on_stream` handler read `data["content"]` but backend emits `data["chunk"]` (all streaming uses `chunk` key)
   - **Impact**: All responses appeared empty even though backend sent them → 0/7 turns passed
   - **Fix**: Changed to read both keys with fallback: `data.get("chunk") or data.get("content", "")`
   - **Test**: 7/7 turns now pass

### Anti-Patterns to Avoid

- **Double Event Emission**: When a feature should emit an event, use ONE source of truth. If socket_handler already handles it, don't also emit from the node.
- **Streaming Fragment Matching**: Use `sub()` not `fullmatch()` for filtering streaming chunks since content may arrive fragmented across multiple events.
- **System Prompt Tool References**: Always verify that every tool name mentioned in the system prompt actually exists in `TOOLS` list before adding documentation about it.
- **Message Event Key Consistency**: Use consistent keys across all socket events (prefer `chunk` for streaming content per OpenAI/LiteLLM convention).

---

## Hard Constraints (from AGENTS.md)

- **NO** HS256 JWT — RS256 only.
- **NO** unauthenticated Redis access.
- **NO** hardcoded MCP server URLs — read from env.
- **NO** guest/anonymous login.
- **NO** plain-text password storage.
- **NO** CORS wildcard (`*`) — use `cors_allowed_origins` from DB/settings.
- **NO** context overflow — enforce token budgets via `app/utils/tokens.py`.
- **NO** double event emission — one source of truth for socket events (socket_handler emits message_complete, not individual nodes).
- Always add memory debug logs in `workflows/graph.py` when modifying LangGraph state transitions.
