# Testing Strategy

## Philosophy
Because testing against production Postgres databases with vectors or massive LangGraph state managers is highly destructive, **Isolated Unit Mocks** are preferred.

## Guidelines
- **Pytest**: Use `pytest` for all backend Python logic. 
- **Mock External Calls**: 
  - Do NOT hit the real OpenAI / LM Studio APIs in standard tests. Mock the `litellm.completion` responses.
  - Mock the `redis.lock` interactions when testing `api/socket_handler.py`.
- **Database Fixtures**: When testing the RAG `pgvector` operators or schema migrations (`alembic`), spin up an isolated postgres Docker test container. Do not run schema operations against development core databases.
- **Circuit Breaker Tests**: Write specific unit tests for `mcp_clients` explicitly invoking `TimeoutError` exceptions to ensure the circuit breaker returns a graceful error dict without crashing the graph state.

## Scenario Coverage (Mandatory)
All cases defined in `agent_docs/user_scenarios.md` MUST have corresponding automated tests in the `tests/scenarios/` directory:
1. `test_rag_hallucination_block.py`: Assert that queries falling below `0.7` cosine similarity bypass LiteLLM and return the hardcoded fallback UI.
2. `test_pii_interceptor.py`: Assert that emails, phones, and passwords are masked before LangGraph injection.
3. `test_upload_validation.py`: Assert that PDF, DOCX, and `.exe` payloads return `400 BadRequest`.
4. `test_off_topic_refusal.py`: Assert that casual/irrelevant queries are politely rejected based on system prompts.
5. `test_basic_mcp_tools.py`: Assert that asking for Time and Weather correctly routes to the `basic_tools` MCP server, fetches mock JSON from open-meteo, and returns the formatted response.

## How to Execute the Scenario Tests (The "Clean Slate" Rule)
To prevent "hallucinations" or false positives caused by lingering database state, stale Redis locks, or cached Python wheels, **you MUST rebuild the Docker environment completely clean** before running the test suite.

Do **NOT** run manual Docker commands or attempt to parse raw build logs. 

Execute the automated test runner script from the project root in Windows PowerShell:
```powershell
python scripts/run_clean_tests.py
```

This single script will explicitly handle:
1. `docker-compose down -v` (Destroying all state)
2. `docker-compose build --no-cache` (Rebuilding cleanly)
3. Spinning up the infrastructure.
4. Running Alembic migrations and `seed.py`.
5. Executing the isolated `pytest` suite inside the container.
