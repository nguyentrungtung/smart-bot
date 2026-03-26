import socketio
import logging
import re
from fastapi import HTTPException
from app.config.settings import settings
from app.middleware.auth import verify_jwt_token, session_lock
from app.middleware.pii_scrubber import scrub_pii
from app.workflows.graph import get_agent_graph
from app.multimodal.capabilities import get_capabilities
from app.multimodal.processor import MultimodalProcessor
from app.schemas.socket_io import MessageIn
import jwt
import uuid
from app.utils.redis import get_redis
from app.memory.chat_history import ChatHistoryTracker
from app.utils.db import get_pool
from langchain_core.messages import HumanMessage, AIMessage
from contextlib import asynccontextmanager
from app.utils.logger import interaction_id_context, session_id_context

logger = logging.getLogger("socket_handler")

# Strict CORS origin mapping from settings per API specs
sio = socketio.AsyncServer(
    async_mode='asgi',
    cors_allowed_origins=settings.CORS_ORIGINS,
    max_http_buffer_size=10000000,  # 10MB to support large image uploads
    logger=True,
    engineio_logger=True
)

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
        decoded = await verify_jwt_token(token)
        
        async with sio.session(sid) as session:
            session['user_id'] = decoded.get('sub')
            
        logger.info(f"Client {sid} authenticated as user: {session['user_id']}")
        
        # Emit multimodal capabilities to FE
        capabilities = get_capabilities()
        logger.info(f"MULTIMODAL CONFIG for {sid}: {capabilities}")
        await sio.emit('multimodal_config', capabilities, room=sid)
        
        return True
        
    except (jwt.PyJWTError, HTTPException):
        logger.warning(f"Connection rejected: Invalid or blacklisted JWT token for {sid}")
        return False

        
@sio.event
async def disconnect(sid):
    async with sio.session(sid) as session:
        user_id = session.get("user_id")
    logger.info(f"Client disconnected: {sid} (user_id: {user_id})")

@sio.on("message")
async def handle_message(sid, data):

    print(f"--- DEBUG SOCKET: Received message from {sid}: {str(data)[:200]}...")
    """
    Main LangGraph Interaction stream loop with multimodal support.
    """
    # 0. Validate basic fields
    try:
        # CRITICAL: Use 'or' instead of get() default to catch null values passed from client
        session_id = data.get("session_id") or ""
        content = data.get("content", "") or ""
        
        if not session_id:
            logger.warning(f"Validation Error for {sid}: session_id is missing or null.")
            await sio.emit('error', {
                'code': 400,
                'status': 'error',
                'message': "Session synchronization error. Please refresh."
            }, room=sid)
            return
            
    except Exception as e:
        logger.warning(f"Validation Error for {sid}: {str(e)}")
        await sio.emit('error', {
            'code': 400,
            'status': 'error',
            'message': f"Invalid request: {str(e)}"
        }, room=sid)
        return

    # 1. Raw Payload Logging (Pre-processing)
    raw_img = data.get("image")
    raw_aud = data.get("audio")
    print(f"--- [SOCKET_HANDLER] Raw Payload for {sid}: image_len={len(raw_img) if raw_img else 0}, audio_len={len(raw_aud) if raw_aud else 0} ---", flush=True)

    client = await get_redis()

    async with session_lock(client, session_id, timeout=30) as acquired:
        if not acquired:
            await sio.emit('error', {
                'code': 429,
                'status': 'error',
                'message': 'System is processing previous query. Please wait.'
            }, room=sid)
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

        async with sio.session(sid) as session:
            user_id = session.get("user_id")

        from app.utils.tokens import calculate_tokens
        user_tokens = calculate_tokens(input_content)

        interaction_id = str(uuid.uuid4())
        
        # Set tracing context
        sid_token = session_id_context.set(session_id)
        iid_token = interaction_id_context.set(interaction_id)

        msg_id = str(uuid.uuid4())
        inputs = {
            "messages": [HumanMessage(content=input_content, id=msg_id, additional_kwargs={"token_count": user_tokens})],
            "session_id": session_id,
            "user_id": user_id,
            "interaction_id": interaction_id,
            "thinking": [],
            "metadata": {}
        }

        # 3.5 Log User Message & Lazy-Register Session
        db_pool = get_pool()
        history_tracker = ChatHistoryTracker(db_pool)

        # OPTIMIZATION: Check Redis first to see if session is already registered in metadata
        # Prevents redundant DB calls for every single message.
        reg_key = f"session_registered:{session_id}"
        if not await client.get(reg_key):
            await history_tracker.ensure_session_exists(session_id, user_id)
            await client.set(reg_key, "1", ex=86400) # Cache for 24h
        
        user_msg_text = content
        # If content is empty but we have an image, note it
        if not user_msg_text and raw_img:
            user_msg_text = "[Image Upload]"
            
        await history_tracker.log_interaction(
            session_id=session_id,
            role="user",
            content=user_msg_text,
            user_id=user_id,
            socket_id=sid
        )

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
            final_state = {}
            async for chunk in agent_graph.astream(inputs, config, stream_mode="updates"):
                for node_name, state_update in chunk.items():
                    print(f"--- [LANGGRAPH] Node '{node_name}' finished execution ---")
                    
                    if state_update and isinstance(state_update, dict):
                        for k, v in state_update.items():
                            final_state[k] = v
                    else:
                        print(f"--- [LANGGRAPH] Warning: Node '{node_name}' returned non-dict update: {type(state_update)}")
                
                msg_count = len(final_state.get('messages', []))
                print(f"--- DEBUG SOCKET: Step complete ---")
            
            # --- CRITICAL: Fetch real final state from LangGraph to handle reducers (add_messages) correctly ---
            graph_state = await agent_graph.aget_state(config)
            final_state = graph_state.values
            
            # 5. Log Assistant Message
            messages = final_state.get("messages", [])
            if messages and isinstance(messages[-1], AIMessage):
                ai_text = messages[-1].content
                interaction_id = await history_tracker.log_interaction(
                    session_id=session_id,
                    role="assistant",
                    content=ai_text,
                    user_id=user_id,
                    socket_id=sid
                )
                # Send the interaction_id to FE so it can rate this specific message
                print(f"--- DEBUG SOCKET: Logged AI response, interaction_id={interaction_id} ---")
                await sio.emit('message_metadata', {
                    'session_id': session_id,
                    'interaction_id': interaction_id
                }, room=sid)

            print(f"--- DEBUG SOCKET: Finished astream, emitting message_complete ---")
            await sio.emit('message_complete', {'session_id': session_id}, room=sid)

            
        except Exception as e:
            logger.error(f"[{interaction_id}] Graph execution error: {str(e)}")
            await sio.emit('error', {
                'code': 500,
                'status': 'error',
                'message': 'An error occurred during generation.'
            }, room=sid)
        finally:
            # Clear tracing context
            session_id_context.reset(sid_token)
            interaction_id_context.reset(iid_token)

@sio.on("message_rate")
async def handle_rating(sid, data):
    """
    Handles user feedback (good/bad) for a specific AI response.
    """
    interaction_id = data.get("interaction_id")
    rating = data.get("rating") # 'good' or 'bad'
    
    if interaction_id and rating:
        db_pool = get_pool()
        history_tracker = ChatHistoryTracker(db_pool)
        await history_tracker.rate_interaction(interaction_id, rating)
        logger.info(f"SOCKET: Interaction {interaction_id} rated as {rating}")
        await sio.emit('rate_success', {'interaction_id': interaction_id}, room=sid)
