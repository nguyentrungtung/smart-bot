# Gemini CLI System Instructions

You are operating within the local terminal as the Gemini CLI agent for the **Smart-Bot MVP**.

## Core Operational Rules:
1. **Golden Rule**: Treat `AGENTS.md` and `docs/TechDesign-Smart-Bot-MVP.md` as absolute truth.
2. **Context Window Limitations**: Do not attempt to ask the user to paste massive files. Use local tools to `grep` or read specific directories as needed.
3. **Windows 11 PowerShell**: The host OS is Windows. All CLI commands MUST be PowerShell compatible. NEVER use Unix commands like `ls`, `grep`, `export`, or `source venv/bin/activate`. Use native PowerShell equivalents or python abstraction.
4. **Python Types**: You must generate robust Python 3.11+ code utilizing full Type Hinting (`str | None`, `TypedDict`, `pydantic.BaseModel`).
5. **Asynchronous Code**: The backbone is Socket.io and FastAPI. All your I/O code (Redis caching, LiteLLM routing, Postgres saving) MUST be `async`. Never use blocking `time.sleep()`, use `asyncio.sleep()`.

## Security Emphases:
- Enforce the MIME Type limit strictly in `schemas/validators.py`.
- Secure the `postMessage` iframe loop securely with explicit string matching.
- **Do not** write tests that connect to production databases. Write mocks or use isolated docker test databases.
