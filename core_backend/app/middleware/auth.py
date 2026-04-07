import jwt
from fastapi import HTTPException
from cryptography.hazmat.primitives import serialization
import os
from contextlib import asynccontextmanager
from app.config.settings import settings
import logging
import time

import time
from passlib.context import CryptContext

logger = logging.getLogger(__name__)

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password):
    return pwd_context.hash(password)

# Preload keys into memory upon startup
_public_key = None
_private_key = None

def get_public_key():
    global _public_key
    if _public_key is None:
        try:
            public_path = os.path.join(settings.KEYS_DIR, "public_key.pem")
            with open(public_path, "rb") as f:
                _public_key = f.read()
        except FileNotFoundError:
            logger.error(f"Cannot find JWT Public Key at {public_path}. Run generate_jwt_keys.py first.")
            raise HTTPException(status_code=500, detail="Internal Auth configuration error")
    return _public_key

def get_private_key():
    global _private_key
    if _private_key is None:
        try:
            private_path = os.path.join(settings.KEYS_DIR, "private_key.pem")
            with open(private_path, "rb") as f:
                _private_key = f.read()
        except FileNotFoundError:
            logger.error(f"Cannot find JWT Private Key at {private_path}. Run generate_jwt_keys.py first.")
            raise HTTPException(status_code=500, detail="Internal Auth configuration error")
    return _private_key

def create_access_token(data: dict) -> str:
    to_encode = data.copy()
    expire = int(time.time()) + (settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60)
    to_encode.update({"exp": expire, "iat": int(time.time()), "type": "access"})
    private_key = get_private_key()
    return jwt.encode(to_encode, private_key, algorithm=settings.JWT_ALGORITHM)

def create_refresh_token(data: dict) -> str:
    to_encode = data.copy()
    expire = int(time.time()) + (settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60)
    to_encode.update({"exp": expire, "iat": int(time.time()), "type": "refresh"})
    private_key = get_private_key()
    return jwt.encode(to_encode, private_key, algorithm=settings.JWT_ALGORITHM)

async def blacklist_token(token: str):
    """
    Adds a token to the Redis blacklist with a TTL equal to its remaining life.
    """
    try:
        from app.utils.redis import get_redis
        redis_client = await get_redis()
        
        # Decode without verification to get exp even if signature is invalid or expired
        # (though we usually only blacklist tokens we just verified)
        payload = jwt.decode(token, options={"verify_signature": False})
        exp = payload.get("exp")
        
        if exp:
            rem = exp - int(time.time())
            if rem > 0:
                # Add a small buffer of 60s to ensure it stays blacklisted until fully expired
                await redis_client.setex(f"blacklist:{token}", rem + 60, "1")
                logger.info(f"Token blacklisted successfully (TTL: {rem}s)")
    except Exception as e:
        logger.error(f"Failed to blacklist token: {str(e)}")

async def is_token_blacklisted(token: str) -> bool:
    """
    Checks if a token exists in the Redis blacklist.
    Fails CLOSED: if Redis is unavailable, all tokens are treated as blacklisted
    to prevent logout-bypass when the cache layer is down.
    """
    try:
        from app.utils.redis import get_redis
        redis_client = await get_redis()
        exists = await redis_client.exists(f"blacklist:{token}")
        return exists > 0
    except Exception as e:
        logger.error(f"Redis blacklist check error — failing closed (deny all): {str(e)}")
        return True  # fail-closed: deny access when we cannot verify

async def verify_jwt_token(token: str) -> dict:
    """
    Validates a JWT coming from the Preact frontend payload using the local RS256 Public Key.
    Also checks against the Redis blacklist.
    """
    # 1. Check blacklist
    if await is_token_blacklisted(token):
        logger.warning(f"Attempted access with blacklisted token")
        raise HTTPException(status_code=401, detail="Token has been revoked/logged out")

    # 2. Standard JWT Validation
    public_key = get_public_key()
    
    try:
        decoded_payload = jwt.decode(
            token, 
            public_key, 
            algorithms=["RS256"]
        )
        return decoded_payload
    except jwt.ExpiredSignatureError:
        logger.warning("Attempted connection with expired JWT")
        raise
    except jwt.InvalidTokenError:
        logger.warning(f"Invalid JWT Token signature attempt")
        raise


@asynccontextmanager
async def session_lock(redis_client, session_id: str, timeout: int = 120):
    """
    Centralized Redis Session Locking with TTL to prevent concurrency issues.
    """
    lock_key = f"lock:{session_id}"
    lock = redis_client.lock(lock_key, timeout=timeout, blocking_timeout=2)
    acquired = False
    try:
        acquired = await lock.acquire()
        yield acquired
    except Exception as e:
        logger.error(f"Redis Lock Error for {session_id}: {str(e)}")
        yield False
    finally:
        if acquired:
            try:
                await lock.release()
            except Exception:
                # Silently ignore if lock already expired or released
                pass


