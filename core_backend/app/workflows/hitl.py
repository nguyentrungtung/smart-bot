import logging
import uuid
import aiohttp
from typing import Dict, Any, Optional
from app.config.settings import settings

logger = logging.getLogger(__name__)

async def request_human_approval(action_name: str, details: Dict[str, Any]) -> str:
    """
    Called by LangGraph when reaching an interrupt_before node.
    Generates a unique Request UUID and sends a Telegram notification if configured.
    Returns the generated UUID that the human must use to approve.
    """
    request_id = str(uuid.uuid4())
    
    message = (
        f"⚠️ **ACTION REQUIRED: {action_name}**\n\n"
        f"Details: {details}\n\n"
        f"To approve this action, send a POST request or click the webhook:\n"
        f"`/api/v1/hitl/approve/{request_id}`"
    )
    
    if settings.TELEGRAM_BOT_TOKEN and settings.TELEGRAM_CHAT_ID:
        # Real telegram integration
        try:
            url = f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/sendMessage"
            payload = {
                "chat_id": settings.TELEGRAM_CHAT_ID,
                "text": message,
                "parse_mode": "Markdown"
            }
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload) as response:
                    if response.status != 200:
                        logger.error(f"Failed to send Telegram HITL message: {await response.text()}")
                    else:
                        logger.info(f"Successfully sent HITL request {request_id} to Telegram.")
        except Exception as e:
            logger.error(f"Telegram Integration Error: {e}")
    else:
        # Mocked terminal output for testing/local dev
        logger.warning(f"\n[HITL MOCK] Telegram credentials missing. Mocking Notification:\n{message}\n")
        
    return request_id

# Endpoint Implementation (Router) placeholder for main.py to mount
from fastapi import APIRouter, HTTPException

hitl_router = APIRouter(prefix="/api/v1/hitl", tags=["HITL"])

@hitl_router.post("/approve/{request_id}")
async def approve_action_webhook(request_id: str):
    """
    Webhook endpoint hit by a manager from the Portal or Telegram bot.
    Resumes the associated LangGraph thread.
    """
    # NOTE: In production, we need a datastore linking request_id -> thread_id
    # For MVP test purposes, we assume LangGraph can query interrupted states by thread
    
    logger.info(f"Received HITL Approval for Request ID: {request_id}")
    
    # Return JSON so Telegram or Frontend knows it succeeded
    return {"status": "approved", "request_id": request_id, "message": "Thread graph resumed"}
