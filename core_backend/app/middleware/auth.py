import jwt
from fastapi import HTTPException
from cryptography.hazmat.primitives import serialization
import os
from contextlib import asynccontextmanager
from app.config.settings import settings
import logging

logger = logging.getLogger(__name__)

# Preload public key into memory upon startup, don't read from disk on every request
_public_key = None

import time

def get_public_key():
    try:
        public_path = os.path.join(settings.KEYS_DIR, "public_key.pem")
        with open(public_path, "rb") as f:
            return f.read() # PyJWT handles the PEM string directly
    except FileNotFoundError:
        logger.error(f"Cannot find JWT Public Key at {public_path}. Run generate_jwt_keys.py first.")
        raise HTTPException(status_code=500, detail="Internal Auth configuration error")

def get_private_key():
    try:
        private_path = os.path.join(settings.KEYS_DIR, "private_key.pem")
        with open(private_path, "rb") as f:
            return f.read()
    except FileNotFoundError:
        logger.error(f"Cannot find JWT Private Key at {private_path}. Run generate_jwt_keys.py first.")
        raise HTTPException(status_code=500, detail="Internal Auth configuration error")

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


def verify_jwt_token(token: str) -> dict:
    """
    Validates a JWT coming from the Preact frontend payload using the local RS256 Public Key.
    Raises jwt.PyJWTError if invalid.
    """
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


