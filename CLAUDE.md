# Claude Code CLI System Instructions

You are operating within the Claude Code terminal environment for the **Smart-Bot MVP** project.

## Your Prime Directives:
1. **READ AGENTS.md FIRST**: This is the master rulebook.
2. **READ THE TECH DESIGN**: Before executing any terminal command to create logic files (`python`, `js`), read `docs/TechDesign-Smart-Bot-MVP.md` so you do not violate the architecture.
3. **FILE CREATION**: Create modular files exactly as defined in the `AGENTS.md` directory structure block.
4. **WINDOWS 11 OS**: You are running in a Windows PowerShell environment. Use Windows-compatible commands (e.g., `Get-Content` instead of `cat`, `rm` works but `Remove-Item` is safer).

## Architectural Standards:
- **Resilience**: Every MCP tool call MUST use `app.connectors.mcp.client.call_mcp_tool` (Circuit Breaker: `mcp_resilience_client`).
- **Local vs MCP**: Standard tools (Time, File System, local DB updates) must go into `app.connectors.local_tools.py`. External tools go to MCP.
- **Context Management**: LM Studio models have a 4096 context. Strictly follow `MAX_HISTORY_TOKENS` (3000) and `SUMMARY_THRESHOLD` (1500) settings.
- **Strict Authentication**: Always use `RS256` (RSA Keypairs) for JWT. Implement token blacklisting via Redis in `app/middleware/auth.py`.
- **Memory Debug**: Maintain detailed memory debug logs in `graph.py` to monitor LangGraph state transitions.

## Docker Usage:
- All services run via `docker-compose`. 
- Proxied LLM calls go through `litellm_proxy` on port 4000.
- Database access is restricted to `postgres` container.
- Use `extra_hosts` for `host.docker.internal` reachability to local model servers.
