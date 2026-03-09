# 🤖 Smart-Bot Master AI Instructions (AGENTS.md)

## 📌 Project Overview
- **Name:** Smart-Bot MVP
- **Goal:** Enterprise-grade AI advisor and internal action-executor (multimodal, iframe widget, RAG, custom MCP tools).
- **Tech Stack:** Preact (Widget), Python 3.11+, LangGraph, LiteLLM, FastAPI/Socket.io, RAGFlow, PostgreSQL (pgvector), Redis, Celery.
- **Current Phase:** Building MVP.

## 🧠 How You (The AI) Should Think
1. **UNDERSTAND FIRST:** NEVER start generating code before you have read the `docs/TechDesign-Smart-Bot-MVP.md` and `docs/PRD-Smart-Bot-MVP.md`.
2. **CHECK PATTERNS:** Before implementing new architecture, consult `agent_docs/code_patterns.md` to ensure your code matches the strict Enterprise Edge Cases defined (Circuit Breakers, Session Locks, Auth).
3. **ASK IF UNSURE:** If the user asks for a feature that contradicts the written constraints (e.g., trying to use direct SQL insert for RAGFlow instead of its REST API), STOP and explicitly warn the user.
4. **THINK ALOUD:** Briefly explain your approach before modifying large chunks of code.

## 🔄 Workflow (Plan -> Execute -> Verify)
1. **PLAN:** Read the user request, identify the files to touch, and write an implementation plan. 
2. **EXECUTE:** Write the code strictly adhering to `agent_docs/tech_stack.md` and `agent_docs/code_patterns.md`.
3. **VERIFY:** Check for type hints (Python), syntax errors, and run relevant test suites or linters. Fix any errors *before* asking the user to review.

## 📁 Context Files
- `/docs/PRD-Smart-Bot-MVP.md`: The WHAT and WHY we are building it.
- `/docs/TechDesign-Smart-Bot-MVP.md`: The HOW we are building it (Architecture & Edge Cases).
- `/agent_docs/*`: Specific, bite-sized rule sets for code generation.

## 🚧 Current State & Roadmap
- [x] Phase 1: Research & Tech Design (Completed)
- [x] Phase 2: Core Backend Setup (Postgres, Redis, RAGFlow, LiteLLM configs)
- [ ] Phase 3: LangGraph Boilerplate & API (Socket.io, Session Locks, PII Middleware)
- [ ] Phase 4: MCP Servers (Xweb tool + Telegram HITL)
- [ ] Phase 5: Preact Multimodal Widget UI

## 🚫 What NOT To Do (Strict Anti-Patterns)
1. **NO** Linux/Bash Syntax: The host OS is Windows 11. All terminal commands must be Windows PowerShell compatible.
2. **NO** Dirty Testing: Never run `pytest` if the Docker state is dirty. Always run `docker-compose down -v` and `docker-compose build --no-cache` before integration tests to prevent hallucinated passing/failing caused by stale SQLite/Postgres data.
3. **NO** `psycopg` raw db connections per thread: Use global connection pooling for LangGraph `MemorySaver`.
4. **NO** Socket.io Wildcard CORS (`*`): Strictly load domains from `.env`/`config.yaml`.
5. **NO** Missing Locks: Always add a `timeout` (TTL) parameter to Redis locks to prevent Zombie sessions.
6. **NO** Custom Authentication Headers for Browser WebSockets: Pass JWT tokens exclusively inside the `auth` payload during Socket IO initialization.
7. **NO** Secret Key JWTs: Do NOT use `HS256` or string secrets for JWT. The project MUST generate and use an **RSA Keypair (RS256)** for signing and decoding tokens.
8. **NO** Raw File Uploads: Strictly reject PDF/DOCX. Only convert Audio via memory buffer (pydub/FFmpeg) before hitting Whisper.
9. **NO** RAG L2 Distance: Always use Cosine Similarity (`<=>`) operator for `pgvector` queries.
