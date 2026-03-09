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

# Global Pool Initialization (Critical for preventing Postgres crash)
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting up Smart-Bot Backend...")
    
    # Create persistent Pool ONCE
    # Using the standard pool max_size = 20
    async with AsyncConnectionPool(settings.DATABASE_URL, max_size=20) as pool:
        app.state.pool = pool
        
        # Initialize the global state checkpoint object
        app.state.checkpointer = AsyncPostgresSaver(pool)
        
        yield
        
    logger.info("Shutting down cleanly, pooling destroyed.")

app = FastAPI(lifespan=lifespan)

# Import the pre-configured SocketIO ASGI dispatcher
from app.api.socket_handler import sio

# Mount the socket.io engine onto the base FastAPI app
app.mount("/", socketio.ASGIApp(sio, other_asgi_app=app))

@app.get("/health")
async def health_check():
    return {"status": "ok", "version": "1.0.0"}
