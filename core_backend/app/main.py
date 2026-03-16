import socketio
from fastapi import FastAPI
from contextlib import asynccontextmanager
from psycopg_pool import AsyncConnectionPool
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from app.config.settings import settings
import logging

# Ensure logging structure is consistent
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("smartbot")

from app.utils import db

# Global Pool Initialization (Critical for preventing Postgres crash)
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting up Smart-Bot Backend...")
    dsn = settings.DATABASE_URL.replace("+psycopg", "")
    try:
        async with AsyncConnectionPool(dsn, max_size=20) as pool_instance:
            db.pool = pool_instance
            db.checkpointer = AsyncPostgresSaver(pool_instance)
            try:
                # Run setup on a dedicated autocommit connection to allow CREATE INDEX CONCURRENTLY
                async with pool_instance.connection() as setup_conn:
                    await setup_conn.set_autocommit(True)
                    setup_saver = AsyncPostgresSaver(setup_conn)
                    await setup_saver.setup()
                logger.info("LangGraph Checkpoint tables verified/created.")
            except Exception as e:
                logger.warning(f"Checkpointer setup failed: {str(e)}. Falling back to MemorySaver.")
                from langgraph.checkpoint.memory import MemorySaver
                db.checkpointer = MemorySaver()
            yield
    except Exception as e:
        logger.error(f"Postgres Connection Failed: {e}. Starting in Memory mode.")
        from langgraph.checkpoint.memory import MemorySaver
        db.pool = None
        db.checkpointer = MemorySaver()
        yield
    logger.info("Shutting down cleanly.")

# 1. Base FastAPI App
fastapi_app = FastAPI(lifespan=lifespan)

# Add CORS Middleware for standard HTTP requests (Auth, Health, etc)
from fastapi.middleware.cors import CORSMiddleware
fastapi_app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 2. Add API Routes
@fastapi_app.get("/health")
async def health_check():
    return {"status": "ok", "version": "1.0.0"}

from app.api.auth_routes import router as auth_router
from app.api.chat_routes import router as chat_router

fastapi_app.include_router(auth_router, prefix="/api/v1")
fastapi_app.include_router(chat_router, prefix="/api/v1")

# 3. Create the final wrapped ASGI App (Socket.IO + FastAPI)
from app.api.socket_handler import sio
app = socketio.ASGIApp(sio, other_asgi_app=fastapi_app)
