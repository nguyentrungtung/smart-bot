import socketio
import logging
import re
from app.config.settings import settings
from app.middleware.auth import verify_jwt_token, session_lock
from app.middleware.pii_scrubber import scrub_pii
from app.workflows.graph import get_agent_graph
from app.multimodal.capabilities import get_capabilities
from app.multimodal.processor import MultimodalProcessor
from app.schemas.socket_io import MessageIn
import jwt
import redis.asyncio as redis
from langchain_core.messages import HumanMessage
from contextlib import asynccontextmanager

logger = logging.getLogger("socket_handler")

# Strict CORS origin mapping from settings per API specs
sio = socketio.AsyncServer(
    async_mode='asgi',
    cors_allowed_origins=settings.CORS_ORIGINS,
    max_http_buffer_size=10000000,  # 10MB to support large image uploads
    logger=True,
    engineio_logger=True
)


# Global Redis Client singleton pool to be initialized
redis_pool = None

async def get_redis():
    global redis_pool
    if redis_pool is None:
        redis_pool = redis.from_url(settings.REDIS_URL, decode_responses=True)
    return redis_pool

@sio.event
async def connect(sid, environ, auth):
    """
    Called upon new Websocket connection attempts.
    Emits multimodal_config so FE knows which features are available.
    """
    if not auth or 'token' not in auth:
        logger.warning(f"Connection rejected: Missing auth token for {sid}")
        return False
        
    token = auth.get('token')
    try:
        decoded = verify_jwt_token(token)
        
        async with sio.session(sid) as session:
            session['user_id'] = decoded.get('sub')
            
        logger.info(f"Client {sid} authenticated as user: {session['user_id']}")
        
        # Emit multimodal capabilities to FE
        capabilities = get_capabilities()
        logger.info(f"MULTIMODAL CONFIG for {sid}: {capabilities}")
        await sio.emit('multimodal_config', capabilities, room=sid)
        
        return True
        
    except jwt.PyJWTError:
        logger.warning(f"Connection rejected: Invalid JWT token signature for {sid}")
        return False
        
@sio.event
async def disconnect(sid):
    logger.info(f"Client disconnected: {sid}")

@sio.on("message")
async def handle_message(sid, data):

    print(f"--- DEBUG SOCKET: Received message from {sid}: {str(data)[:200]}...")
    """
    Main LangGraph Interaction stream loop with multimodal support.
    """
    # 0. Validate basic fields
    try:
        session_id = data.get("session_id", "")
        content = data.get("content", "") or ""
    except Exception as e:
        logger.warning(f"Validation Error for {sid}: {str(e)}")
        await sio.emit('error', {'detail': f"Invalid request: {str(e)}"}, room=sid)
        return

    # 1. Raw Payload Logging (Pre-processing)
    raw_img = data.get("image")
    raw_aud = data.get("audio")
    print(f"--- [SOCKET_HANDLER] Raw Payload for {sid}: image_len={len(raw_img) if raw_img else 0}, audio_len={len(raw_aud) if raw_aud else 0} ---", flush=True)

    client = await get_redis()

    async with session_lock(client, session_id, timeout=30) as acquired:
        if not acquired:
            await sio.emit('error', {'detail': 'System is processing previous query...'}, room=sid)
            return

        # 2. Sanitize text input (PII Scrubbing)
        content = scrub_pii(content)
        
        # 3. Build multimodal content using consolidated processor
        input_content = MultimodalProcessor.format_message_content(
            text=content, 
            attachments={"image": raw_img, "audio": raw_aud}
        )
        
        capabilities = get_capabilities()
        logger.info(
            f"SOCKET: Built input content — type={'multimodal' if isinstance(input_content, list) else 'text'}, "
            f"capabilities={capabilities}"
        )

        inputs = {
            "messages": [HumanMessage(content=input_content)],
            "session_id": session_id,
            "thinking": [],
            "metadata": {}
        }

        config = {
            "configurable": {
                "thread_id": session_id,
                "sio": sio,
                "sid": sid
            }
        }

        
        # 4. Stream from LangGraph (with Short-Term Memory via Checkpointer)
        try:
            agent_graph = get_agent_graph()
            logger.info(f"MEMORY DEBUG: Invoking graph with thread_id={session_id}, input messages count={len(inputs['messages'])}")
            print(f"--- DEBUG SOCKET: Starting astream for {session_id} (thread_id={session_id}) ---")
            async for chunk in agent_graph.astream(inputs, config, stream_mode="values"):
                msg_count = len(chunk.get('messages', []))
                print(f"--- DEBUG SOCKET: Yielded a chunk (total messages in state: {msg_count}) ---")
                pass
            
            print(f"--- DEBUG SOCKET: Finished astream, emitting message_complete ---")
            await sio.emit('message_complete', {'session_id': session_id}, room=sid)

            
        except Exception as e:
            logger.error(f"Graph execution error: {str(e)}")
            await sio.emit('error', {'detail': 'An error occurred during generation.'}, room=sid)
