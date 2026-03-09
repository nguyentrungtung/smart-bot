import socketio
import logging
from app.config.settings import settings
from app.middleware.auth import verify_jwt_token
import jwt
import redis.asyncio as redis
from contextlib import asynccontextmanager

logger = logging.getLogger("socket_handler")

# Strict CORS origin mapping from settings per API specs
sio = socketio.AsyncServer(
    async_mode='asgi',
    cors_allowed_origins=settings.CORS_ORIGINS,
    logger=False, # Disable verbose logging for prod
    engineio_logger=False
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
    The Frontend MUST pass a valid JWT in the auth payload because headers are dropped in Browser WS.
    """
    if not auth or 'token' not in auth:
        logger.warning(f"Connection rejected: Missing auth token for {sid}")
        return False # Disconnects immediately
        
    token = auth.get('token')
    try:
        # RS256 Validation against Public Key
        decoded = verify_jwt_token(token)
        
        # Save user to session scope
        async with sio.session(sid) as session:
            session['user_id'] = decoded.get('sub')
            
        logger.info(f"Client {sid} authenticated as user: {session['user_id']}")
        return True # Allowed
        
    except jwt.PyJWTError:
        logger.warning(f"Connection rejected: Invalid JWT token signature for {sid}")
        return False
        
@sio.event
async def disconnect(sid):
    logger.info(f"Client disconnected: {sid}")

@sio.event
async def handle_message(sid, data):
    """
    Main LangGraph Interaction stream loop.
    Enforces Strict Session Locks with TTLs.
    """
    session_id = data.get("session_id")
    if not session_id:
        await sio.emit('error', {'detail': 'session_id is required'}, room=sid)
        return
        
    client = await get_redis()
    lock_key = f"lock:{session_id}"
    
    # 30-Second TTL Mandatory (To prevent Zombie Locks if crashes occur)
    async with client.lock(lock_key, timeout=30, blocking_timeout=2) as acquired:
        if not acquired:
            await sio.emit('error', {'detail': 'System is processing previous query...'}, room=sid)
            return
            
        # TODO: Await actual lang_graph stream here and pipe chunks back
        await sio.emit('message_stream', {'chunk': "Acknowledged..."}, room=sid)
