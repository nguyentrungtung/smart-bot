# Gemini CLI System Instructions

You are operating within the local terminal as the Gemini CLI agent for the **Smart-Bot MVP**.

## Core Operational Rules:
1. **Golden Rule**: Treat `AGENTS.md` and `docs/TechDesign-Smart-Bot-MVP.md` as absolute truth.
2. **Context Window Limitations**: LM Studio models often have a 4096 context. Strictly follow the `MAX_HISTORY_TOKENS` (3000) and `SUMMARY_THRESHOLD` (1500) settings in `settings.py`.
3. **Windows 11 PowerShell**: The host OS is Windows. All CLI commands MUST be PowerShell compatible.
4. **Python Types**: Utilize full Type Hinting (`str | None`, `TypedDict`, `pydantic.BaseModel`).
5. **Asynchronous Code**: All I/O (Redis, LiteLLM, Postgres) MUST be `async`.

## Security & Architecture Emphases:
- **Resilience**: Every MCP tool call MUST use `app.connectors.mcp.client.call_mcp_tool` (Circuit Breaker: `mcp_resilience_client`).
- **Local vs MCP**: Tools that don't need external data (System Time, Local Files, logic-only) must remain in `app.connectors.local_tools.py`.
- **Strict Authentication**: JWT MUST use `RS256` (RSA). Token Blacklisting via Redis with TTL in `app/middleware/auth.py`.
- **Multimodal Standard**: Always use `app.multimodal` package. Handle Vision (images) and Audio (voice) via the `processor`.
- **Memory Management**: Detailed memory debug logs in `graph.py` must be maintained to monitor LangGraph state transitions.

## Directory Logic:
- `api/socket_handler.py`: Real-time streaming and PII scrubbing gateway.
- `workflows/nodes/generate.py`: Main LLM node. Handles token usage debug & trimming.
- `workflows/nodes/tools.py`: Unified entry for both local and external tools.
- `workflows/nodes/summarizer.py`: Aggressive context management for local models.
