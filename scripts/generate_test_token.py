# scripts/generate_test_token.py
import jwt
import time
import os
import sys
from pathlib import Path

# Add core_backend to path to import settings
sys.path.append(str(Path(__file__).parent.parent / "core_backend"))
from app.config.settings import settings

# Paths to the keys generated during verification
KEYS_DIR = Path("./.keys")
PRIVATE_KEY_PATH = KEYS_DIR / "private_key.pem"

def generate_token(user_id="test_user_123"):
    if not PRIVATE_KEY_PATH.exists():
        print("Private key not found! Run generate_jwt_keys.py first.")
        return None
        
    private_key = PRIVATE_KEY_PATH.read_text()
    
    expires_delta = settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60
    
    payload = {
        "sub": user_id,
        "name": "Test User",
        "role": "admin",
        "iat": int(time.time()),
        "exp": int(time.time()) + expires_delta,
    }
    
    token = jwt.encode(payload, private_key, algorithm="RS256")
    return token

if __name__ == "__main__":
    token = generate_token()
    if token:
        print("\n--- NEW TEST JWT TOKEN (RS256) ---\n")
        print(token)
        print("\n--- END TOKEN ---\n")
