import socketio
import asyncio
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from app.schemas.api_response import APIResponse, ErrorResponse
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
from app.schemas.api_response import APIResponse

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
@fastapi_app.get("/health", response_model=APIResponse[dict])
async def health_check():
    return {
        "code": 200,
        "status": "success",
        "message": "Smart-Bot API refershly serving.",
        "data": {"status": "ok", "version": "1.0.0"}
    }

# 4. Global Exception Handlers
@fastapi_app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content=ErrorResponse(
            code=exc.status_code,
            status="error",
            message=exc.detail if isinstance(exc.detail, str) else str(exc.detail)
        ).model_dump()
    )

@fastapi_app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=422,
        content=ErrorResponse(
            code=422,
            status="error",
            message="Validation error",
            errors=exc.errors()
        ).model_dump()
    )

@fastapi_app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled Exception: {str(exc)}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content=ErrorResponse(
            code=500,
            status="error",
            message="Đã có lỗi hệ thống xảy ra. Vui lòng thử lại sau."
        ).model_dump()
    )

from app.api.auth_routes import router as auth_router
from app.api.chat_routes import router as chat_router

fastapi_app.include_router(auth_router, prefix="/api/v1")
fastapi_app.include_router(chat_router, prefix="/api/v1")

# 3. Create the final wrapped ASGI App (Socket.IO + FastAPI)
from app.api.socket_handler import sio
app = socketio.ASGIApp(sio, other_asgi_app=fastapi_app)
