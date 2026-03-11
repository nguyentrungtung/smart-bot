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
    
    # Create persistent Pool ONCE
    # Using the standard pool max_size = 20
    async with AsyncConnectionPool(settings.DATABASE_URL, max_size=20, kwargs={"autocommit": True}) as pool_instance:
        db.pool = pool_instance


        
        # Initialize the global state checkpoint object
        db.checkpointer = AsyncPostgresSaver(pool_instance)
        
        # REQUIRED: Create checkpoint tables if they do not exist
        try:
            # We explicitly setup the checkpointer
            await db.checkpointer.setup()
            logger.info("LangGraph Checkpoint tables verified/created.")
        except Exception as e:
            logger.warning(f"Checkpointer setup failed: {str(e)}. Falling back to MemorySaver.")
            from langgraph.checkpoint.memory import MemorySaver
            db.checkpointer = MemorySaver()


        
        yield
        
    logger.info("Shutting down cleanly, pooling destroyed.")

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
fastapi_app.include_router(auth_router)

# 3. Create the final wrapped ASGI App (Socket.IO + FastAPI)
from app.api.socket_handler import sio
app = socketio.ASGIApp(sio, other_asgi_app=fastapi_app)

