import socketio
import asyncio
from fastapi import FastAPI
from contextlib import asynccontextmanager
from psycopg_pool import AsyncConnectionPool
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from app.config.settings import settings
import logging

# Ensure logging structure is consistent
import langchain
from app.utils.logger import setup_logger
langchain.debug = settings.DEBUG_LANGCHAIN

logger = setup_logger("smartbot", level=getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO))

from app.utils import db

# Global Pool Initialization (Critical for preventing Postgres crash)
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("🚀 Starting up Smart-Bot Backend...")
    dsn = settings.DATABASE_URL.replace("+psycopg", "")
    
    try:
        # 1. Initialize Connection Pool
        async with AsyncConnectionPool(dsn, max_size=20) as pool_instance:
            db.pool = pool_instance
            
            # 2. Setup Checkpointer Tables (LangGraph)
            logger.info("Init LangGraph Postgres Checkpointer...")
            setup_success = False
            for attempt in range(1, 4):
                try:
                    async with pool_instance.connection() as setup_conn:
                        await setup_conn.set_autocommit(True)
                        setup_saver = AsyncPostgresSaver(setup_conn)
                        await setup_saver.setup()
                        setup_success = True
                        break
                except Exception as e:
                    logger.warning(f"⚠️ Checkpointer setup attempt {attempt} failed: {e}")
                    if attempt < 3:
                        await asyncio.sleep(2) # Wait for DB to be ready
            
            if setup_success:
                db.checkpointer = AsyncPostgresSaver(pool_instance)
                logger.info("✅ LangGraph Checkpoint tables verified/created.")
            else:
                logger.error("❌ All checkpointer setup attempts failed. Falling back to MemorySaver.")
                from langgraph.checkpoint.memory import MemorySaver
                db.checkpointer = MemorySaver()
            
            yield
    except Exception as e:
        logger.error(f"❌ Postgres Connection Failed: {e}. Starting in Memory mode.")
        from langgraph.checkpoint.memory import MemorySaver
        db.pool = None
        db.checkpointer = MemorySaver()
        yield
    logger.info("Stopping Smart-Bot Backend...")



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
