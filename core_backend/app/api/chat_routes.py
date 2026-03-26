from fastapi import APIRouter, HTTPException, Depends, status, Body, BackgroundTasks
from fastapi.security import OAuth2PasswordBearer
from app.middleware.auth import verify_jwt_token
from app.memory.chat_history import ChatHistoryTracker
from app.utils.db import get_pool
from pydantic import BaseModel, Field
from app.schemas.api_response import APIResponse
import uuid
import jwt
import logging

logger = logging.getLogger("chat_routes")
router = APIRouter(prefix="/chat", tags=["chat"])
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="api/v1/auth/login", auto_error=False)

class NewSessionRequest(BaseModel):
    old_session_id: str | None = Field(None, description="The session ID to be cleaned up before starting a new one")

class NewSessionResponse(BaseModel):
    session_id: str = Field(..., description="Newly created UUID v4 session ID")
    user_id: str = Field(..., description="The user linked to this session")

class CleanupResponse(BaseModel):
    details: dict

async def get_current_user_id(token: str = Depends(oauth2_scheme)) -> str:
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        payload = await verify_jwt_token(token)
        return payload.get("sub")
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid token")

@router.post("/new-session", response_model=APIResponse[NewSessionResponse], status_code=status.HTTP_201_CREATED)
async def create_new_session(
    background_tasks: BackgroundTasks,
    payload: NewSessionRequest | None = None,
    user_id: str = Depends(get_current_user_id)
):
    """
    Creates a new Chat Session (thread_id) to reset context.
    Ensures LangGraph starts with a clean state.
    """
    session_id = str(uuid.uuid4())
    
    db_pool = get_pool()
    tracker = ChatHistoryTracker(db_pool)
    
    # 1. Register session in metadata table for persistence
    await tracker.create_session(session_id, user_id)
    
    # 2. Cleanup old session checkpoints if requested (Background Task)
    if payload and payload.old_session_id:
        logger.info(f"Queueing cleanup for old session: {payload.old_session_id}")
        background_tasks.add_task(tracker.delete_session_checkpoints, payload.old_session_id)
    
    logger.info(f"New session created: {session_id} for user {user_id}")
    
    return {
        "code": 201,
        "status": "success",
        "message": "New session created successfully.",
        "data": {
            "session_id": session_id,
            "user_id": user_id
        }
    }

@router.delete("/history", response_model=APIResponse[CleanupResponse], status_code=status.HTTP_200_OK)
async def cleanup_history(days: int = 7, user_id: str = Depends(get_current_user_id)):
    """
    Cleanup Job: Deletes chat history and checkpoints older than X days.
    """
    db_pool = get_pool()
    tracker = ChatHistoryTracker(db_pool)
    
    try:
        results = await tracker.cleanup_history(days=days)
        return {
            "code": 200,
            "status": "success",
            "message": "Maintenance cleanup completed.",
            "data": {
                "details": results
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Cleanup failed: {str(e)}")
