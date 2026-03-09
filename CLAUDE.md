# Claude Code CLI System Instructions

You are operating within the Claude Code terminal environment for the **Smart-Bot MVP** project.

## Your Prime Directives:
1. **READ AGENTS.md FIRST**: This is the master rulebook.
2. **READ THE TECH DESIGN**: Before executing any terminal command to create logic files (`python`, `js`), read `docs/TechDesign-Smart-Bot-MVP.md` so you do not violate the architecture.
3. **FILE CREATION**: Create modular files exactly as defined in the `docs/research-smart-bot.md` directory structure block.
4. **COMMAND EXECUTION**: 
   - **WINDOWS 11 OS**: You are running in a Windows PowerShell environment. You MUST use Windows-compatible commands.
   - Use `python -m venv venv` and `.\venv\Scripts\Activate.ps1` (NEVER `source venv/bin/activate`).
   - Use `.env` files or Windows syntax for environment variables (NEVER `export VAR=x`).
   - If a package is missing, explicitly ask the user for permission to `pip install` it and add it to `requirements.txt`.
5. **DOCKER**: This project relies heavily on `docker-compose`. Ensure any new service logic is accurately mapped in a `docker-compose.yml` file.

## Specific AI Coding Weaknesses to Avoid:
- **Do not hallucinate vector math**: Use exact `pgvector` Cosine Similarity.
- **Do not overcomplicate LangGraph**: Keep Nodes pure and stateless logic functions. All State modifications must strictly type-check against `state.py`.
- **Do not leak PII**: Ensure `middleware/pii_scrubber.py` is called before LiteLLM.
- **Do not use basic JWT strings**: Always configure `PyJWT` with the `RS256` algorithm and utilize generated `.pem` RSA key pairs for logic involving `auth.py`.
