# Docker Testing & Local Run Guide

## Philosophy
To ensure all AI agents and developers execute code in an identical, isolated environment, **all local testing MUST be performed via Docker Compose**. 
Do **NOT** run `uvicorn` or `python` directly on the host machine OS to test the full stack, as it will lead to environment variables and dependency mismatches (e.g., missing Redis or `pgvector` extensions).

## Core Docker Commands

When setting up or testing the architecture, use these exact commands:

### 1. Build & Spin Up the Core Infrastructure
(Starts Postgres with pgvector, Redis, LiteLLM, and RAGFlow)
```bash
docker-compose --profile infra up -d --build
```

### 2. Run the Main Backend Action
(Starts the FastAPI/LangGraph `core_backend` and the async Celery workers)
```bash
docker-compose --profile backend up -d --build
```

### 3. Check Real-Time Logs
Always verify the services are running without crashing loops:
```bash
# Check all logs
docker-compose logs -f

# Check specific backend errors (e.g., checking if the Connection Pool initialized correctly)
docker-compose logs -f core_backend
```

### 4. Run Isolated Pytest Suite (Clean State Requirement)
To prevent debugging hallucinations caused by stale database records or cached code, **you MUST destroy and rebuild the container without cache** before executing a final test run.

Avoid typing manual Docker commands. Always use the provided automation script:

```powershell
# Executes teardown, no-cache build, migrations, seeding, and pytest automatically
python scripts/run_clean_tests.py
```

### 5. Tear Down and Wipe State
Always clean up after yourself when a session is complete:
```powershell
docker-compose down -v
```

## AI Agent Rules for Testing
1. **Never assume dependencies exist**: If you write a new test that requires a DB, ensure you tell the user to run `docker-compose --profile infra up -d` first.
2. **Postgres pgvector Warning**: Standard Postgres images do NOT have the vector extension. The `docker-compose.yml` MUST use the official `pgvector/pgvector:pg16` image or building it from a Dockerfile. If you try to run pgvector tests on local SQLite, they will fail spectacularly.
3. **Wait for DB**: When writing backend startup tests, always include retry logic (e.g., `tenacity` or a bash `wait-for-it` script) to wait for Postgres and Redis to accept connections before initializing the application pools.
