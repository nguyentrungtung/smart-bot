import asyncio
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
    max_http_buffer_size=50000000,  # 50MB: safely handle 10MB audio base64 (~33% larger) + overhead, AND large images
    logger=False,          # Disable socket.io packet logging (floods logs with base64)
    engineio_logger=False  # Disable engine.io transport logging
)

@sio.event
async def connect(sid, environ, auth):
    """
    Called upon new Websocket connection attempts.
    Emits multimodal_config so FE knows which features are available.
    """
    if not auth or 'token' not in auth:
        logger.warning(f"[SOCKET OPEN DENIED] {sid}: Missing auth token")
        return False

    token = auth.get('token')
    try:
        decoded = await verify_jwt_token(token)

        async with sio.session(sid) as session:
            session['user_id'] = decoded.get('sub')

        logger.info(f"[SOCKET OPEN] {sid} authenticated as user: {decoded.get('sub')}")

        # Emit multimodal capabilities to FE
        capabilities = get_capabilities()
        logger.debug(f"[{sid}] Sending multimodal_config: {capabilities}")
        await sio.emit('multimodal_config', capabilities, room=sid)

        return True

    except (jwt.PyJWTError, HTTPException):
        logger.warning(f"[SOCKET OPEN DENIED] {sid}: Invalid or blacklisted JWT token")
        return False

        
@sio.event
async def disconnect(sid):
    async with sio.session(sid) as session:
        user_id = session.get("user_id")
    logger.info(f"[SOCKET CLOSE] {sid} (user_id: {user_id})")

@sio.on("message")
async def handle_message(sid, data):
    """
    Main Socket.IO message handler: Chrome/browser → backend → LangGraph → response.

    Pipeline Steps (numbered for easy debugging):
      1. VALIDATE  — Check session_id, content format
      2. EXTRACT   — Get image, audio, text from payload
      3. SANITIZE  — PII scrub text
      4. PREPARE   — STT (if audio), image blocks, multimodal content (NO LOCK YET)
      5. LOCK      — Acquire Redis session lock (only NOW, after expensive STT)
      6. STREAM    — LangGraph astream with message_complete callbacks

    Key: STT is OUTSIDE the lock to avoid 429 errors when processing consecutive audio messages.
    """
    pfx = sid[:8]  # Short session ID for logs

    # ─ STEP 1: VALIDATE ───────────────────────────────────────────────────────
    try:
        session_id = data.get("session_id") or ""
        content = data.get("content", "") or ""

        if not session_id:
            logger.warning(f"[{pfx}] STEP 1/6 VALIDATE: session_id missing")
            await sio.emit(
                "error",
                {"code": 400, "status": "error", "message": "Session synchronization error. Please refresh."},
                room=sid,
            )
            return

        logger.info(f"[{pfx}] STEP 1/6 VALIDATE ✓ session_id={session_id[:12]}...")

    except Exception as e:
        logger.warning(f"[{pfx}] STEP 1/6 VALIDATE ✗ {str(e)}")
        await sio.emit(
            "error",
            {"code": 400, "status": "error", "message": f"Invalid request: {str(e)}"},
            room=sid,
        )
        return

    # ─ STEP 2: EXTRACT ────────────────────────────────────────────────────────
    raw_img = data.get("image")
    raw_aud = data.get("audio")
    has_image = bool(raw_img)
    has_audio = bool(raw_aud)
    logger.info(
        f"[{pfx}] STEP 2/6 EXTRACT: text={len(content)}chars, image={has_image}, audio={has_audio}"
    )

    # ─ STEP 3: SANITIZE ───────────────────────────────────────────────────────
    content = scrub_pii(content)
    logger.debug(f"[{pfx}] STEP 3/6 SANITIZE ✓ PII scrubbed")

    # ─ STEP 4: PREPARE (STT + multimodal blocks — BEFORE lock) ─────────────────
    logger.info(f"[{pfx}] STEP 4/6 PREPARE: building multimodal content (STT if audio)...")
    try:
        input_content = await MultimodalProcessor.format_message_content(
            text=content,
            attachments={"image": raw_img, "audio": raw_aud},
            session_id=session_id,
        )
        capabilities = get_capabilities()
        content_type = "multimodal" if isinstance(input_content, list) else "text"
        logger.info(
            f"[{pfx}] STEP 4/6 PREPARE ✓ {content_type} content ready, {capabilities}"
        )
    except Exception as e:
        logger.error(f"[{pfx}] STEP 4/6 PREPARE ✗ {str(e)}")
        await sio.emit(
            "error",
            {"code": 500, "status": "error", "message": "Lỗi xử lý nội dung"},
            room=sid,
        )
        return

    client = await get_redis()

    # ─ STEP 5: LOCK ────────────────────────────────────────────────────────────
    # Lock timeout = 120s to cover LLM generation (STT is already done in STEP 4).
    # This prevents concurrent processing of the same session.
    logger.info(f"[{pfx}] STEP 5/6 LOCK: acquiring Redis session lock (120s timeout)...")
    async with session_lock(client, session_id, timeout=120) as acquired:
        if not acquired:
            logger.warning(f"[{pfx}] STEP 5/6 LOCK: failed to acquire (session busy)")
            await sio.emit(
                "error",
                {
                    "code": 429,
                    "status": "error",
                    "message": "System is processing previous query. Please wait.",
                },
                room=sid,
            )
            return

        logger.info(f"[{pfx}] STEP 5/6 LOCK ✓ acquired")

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
            "metadata": {},
            "tool_call_count": 0,
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
        # For image-only or audio-only messages, log a meaningful label.
        # For audio, extract the STT transcription if available.
        if not user_msg_text:
            if raw_aud:
                # Extract transcription text from the processed content blocks
                if isinstance(input_content, list):
                    transcribed = next(
                        (b.get("text", "") for b in input_content
                         if isinstance(b, dict) and b.get("type") == "text"
                         and b.get("text", "").startswith("[Giọng nói")),
                        None
                    )
                    user_msg_text = transcribed or "[Voice Message]"
                else:
                    user_msg_text = "[Voice Message]"
            elif raw_img:
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

        # ─ STEP 6: STREAM ──────────────────────────────────────────────────────────
        # LangGraph astream with message_complete callbacks.
        # KEY: We release the session lock as soon as the agent emits message_complete.
        # Background nodes (summarizer, profile_analyzer) continue running in a
        # detached asyncio task so they don't block the next user message.
        logger.info(f"[{pfx}] STEP 6/6 STREAM: starting LangGraph astream...")
        try:
            agent_graph = get_agent_graph()
            logger.debug(
                f"[{pfx}] Graph invoke: thread_id={session_id}, messages={len(inputs['messages'])}"
            )
            final_state = {}
            response_sent = False  # Guard: emit message_complete only once
            _release_lock_early = False  # Signal to break outer astream loop
            astream_gen = agent_graph.astream(inputs, config, stream_mode="updates")

            async for chunk in astream_gen:
                for node_name, state_update in chunk.items():
                    logger.debug(f"[LANGGRAPH] Node '{node_name}' finished execution")

                    if isinstance(state_update, dict):
                        # Empty dict {} is a valid no-op return from background nodes
                        for k, v in state_update.items():
                            final_state[k] = v
                    elif state_update is not None:
                        logger.warning(f"Node '{node_name}' returned unexpected update type: {type(state_update)}")

                    # ── UX FIX: emit message_complete as soon as agent produces a
                    # final response (no pending tool calls). This unblocks the widget
                    # immediately — background nodes (summarizer, profile_analyzer)
                    # continue running without the client waiting for them.
                    if not response_sent and node_name == "agent":
                        msgs = state_update.get("messages", []) if isinstance(state_update, dict) else []
                        last = msgs[-1] if msgs else None
                        has_tool_calls = (
                            last is not None
                            and hasattr(last, "tool_calls")
                            and bool(last.tool_calls)
                        )
                        if last is not None and not has_tool_calls:
                            # Log interaction before releasing the client
                            ai_text = last.content if isinstance(last, AIMessage) else ""
                            if ai_text:
                                logged_iid = await history_tracker.log_interaction(
                                    session_id=session_id,
                                    role="assistant",
                                    content=ai_text,
                                    user_id=user_id,
                                    socket_id=sid
                                )
                                logger.debug(f"Logged AI response early, interaction_id={logged_iid}")
                                await sio.emit('message_metadata', {
                                    'session_id': session_id,
                                    'interaction_id': logged_iid
                                }, room=sid)
                            logger.info(f"[{pfx}] About to emit message_complete...")
                            try:
                                await sio.emit('message_complete', {'session_id': session_id}, room=sid)
                                logger.info(f"[{pfx}] ✓ message_complete emitted successfully")
                            except Exception as emit_err:
                                logger.error(f"[{pfx}] ✗ FAILED to emit message_complete: {emit_err}")
                            response_sent = True

                            # ── LOCK RELEASE: drain remaining background nodes in a
                            # detached task so the session lock is freed immediately.
                            # This prevents 429 when the user sends the next message
                            # while profile_analyzer / summarizer are still running.
                            # NOTE: We must break BOTH loops (inner for + outer async for)
                            # to exit the session_lock context manager.
                            async def _drain_background_nodes(gen):
                                try:
                                    async for bg_chunk in gen:
                                        for bg_node, _ in bg_chunk.items():
                                            logger.debug(f"[BACKGROUND] Node '{bg_node}' complete (detached)")
                                except Exception as bg_err:
                                    logger.warning(f"[BACKGROUND] Node drain error (non-fatal): {bg_err}")

                            asyncio.create_task(_drain_background_nodes(astream_gen))
                            _release_lock_early = True
                            break  # break inner for loop

                logger.debug(f"Node '{node_name}' step complete")

                if _release_lock_early:
                    break  # break outer async for loop → exits session_lock context → releases lock

            # Fallback: if message_complete was never sent (e.g. guard bypass path)
            if not response_sent:
                # --- Fetch real final state from LangGraph to handle reducers correctly ---
                graph_state = await agent_graph.aget_state(config)
                final_state = graph_state.values

                messages = final_state.get("messages", [])
                if messages and isinstance(messages[-1], AIMessage):
                    ai_text = messages[-1].content
                    logged_iid = await history_tracker.log_interaction(
                        session_id=session_id,
                        role="assistant",
                        content=ai_text,
                        user_id=user_id,
                        socket_id=sid
                    )
                    logger.debug(f"Logged AI response (fallback), interaction_id={logged_iid}")
                    await sio.emit('message_metadata', {
                        'session_id': session_id,
                        'interaction_id': logged_iid
                    }, room=sid)

                logger.info(f"[{pfx}] Finished astream, emitting message_complete (fallback)...")
                try:
                    await sio.emit('message_complete', {'session_id': session_id}, room=sid)
                    logger.info(f"[{pfx}] ✓ message_complete emitted (fallback path)")
                except Exception as emit_err:
                    logger.error(f"[{pfx}] ✗ FAILED to emit message_complete (fallback): {emit_err}")

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
