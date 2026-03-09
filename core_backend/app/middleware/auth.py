import jwt
from fastapi import HTTPException
from cryptography.hazmat.primitives import serialization
import os
from app.config.settings import settings
import logging

logger = logging.getLogger(__name__)

# Preload public key into memory upon startup, don't read from disk on every request
_public_key = None

def get_public_key():
    global _public_key
    if _public_key is not None:
        return _public_key
        
    try:
        public_path = os.path.join(settings.KEYS_DIR, "public_key.pem")
        with open(public_path, "rb") as f:
            _public_key = serialization.load_pem_public_key(f.read())
        return _public_key
    except FileNotFoundError:
        logger.error(f"Cannot find JWT Public Key at {public_path}. Run generate_jwt_keys.py first.")
        raise HTTPException(status_code=500, detail="Internal Auth configuration error")

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
