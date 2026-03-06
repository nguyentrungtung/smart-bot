# Smart-Bot Tech Stack

## Core Backend
- **Language**: Python 3.11+
- **Agent Orchestrator**: LangGraph
- **API Framework**: FastAPI
- **Real-Time Streaming**: `python-socketio` (AsyncServer)
- **Model Router**: LiteLLM Proxy
- **Local Fallback**: LM Studio

## Data Layer
- **Relational & Vector DB**: PostgreSQL 16 with `pgvector`
- **Migration Tool**: Alembic
- **Memory & Cache**: Redis (Vector DB Support)
- **Background Jobs**: Celery + Redis broker
- **Knowledge Ingestion**: RAGFlow (Async integration via REST API)

## Microservices (Tooling)
- **Protocol**: Model Context Protocol (MCP) Python SDK
- **Transport**: Server-Sent Events (SSE)

## Frontend (Widget)
- **Framework**: Preact
- **Isolation**: Iframe embedded via parent `<script>` tag
- **Communication**: 2-way `postMessage` (for Resize and Auth) + WebSockets (for Streaming)

## Infrastructure
- **Orchestration**: Docker Compose
- **Gateway**: Nginx/Traefik
