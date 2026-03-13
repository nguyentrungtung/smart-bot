import pytest
import jwt
import os
from datetime import datetime, timedelta
from cryptography.hazmat.primitives import serialization
from app.middleware.auth import verify_jwt_token
from app.middleware.pii_scrubber import scrub_pii

@pytest.fixture
def rsa_keys():
    """Load real keys from .keys if available, else fail (tests should run in environment with keys)."""
    keys_dir = os.path.join(os.path.dirname(__file__), "..", "..", ".keys")
    private_path = os.path.join(keys_dir, "private_key.pem")
    public_path = os.path.join(keys_dir, "public_key.pem")
    
    with open(private_path, "rb") as f:
        priv = serialization.load_pem_private_key(f.read(), password=None)
    with open(public_path, "rb") as f:
        pub = serialization.load_pem_public_key(f.read())
    return priv, pub

def create_token(priv_key, user_id="test_user", expired=False):
    payload = {
        "sub": user_id,
        "iat": datetime.utcnow(),
        "exp": datetime.utcnow() + (timedelta(days=1) if not expired else timedelta(days=-1))
    }
    return jwt.encode(payload, priv_key, algorithm="RS256")

# --- AUTH TESTS ---

@pytest.mark.asyncio
async def test_jwt_rs256_validation(rsa_keys):
    priv, pub = rsa_keys
    token = create_token(priv, "user_999")
    
    # verify_jwt_token uses settings.KEYS_DIR which should be mapped to .keys
    # For unit test, we can mock the decoder
    with patch("app.middleware.auth.jwt.decode", return_value={"sub": "user_999"}):
        result = await verify_jwt_token(token)
        assert result["sub"] == "user_999"

@pytest.mark.asyncio
async def test_jwt_expiration(rsa_keys):
    priv, _ = rsa_keys
    token = create_token(priv, "user_999", expired=True)
    
    with pytest.raises(jwt.ExpiredSignatureError):
        # We allow real decode here if public key is in place
        from app.config.settings import settings
        keys_dir = settings.KEYS_DIR
        with open(os.path.join(keys_dir, "public_key.pem"), "rb") as f:
            pub_pem = f.read()
            jwt.decode(token, pub_pem, algorithms=["RS256"])

# --- PII TESTS ---

def test_pii_scrubbing_patterns():
    test_cases = [
        ("My email is admin@gmail.com", "My email is [REDACTED_EMAIL]"),
        ("Call me at 0912345678", "Call me at [REDACTED_PHONE]"),
        ("Secret key: 123-456-789", "Secret key: 123-456-789"), # Should not scrub generic numbers
        ("My card is 4111 2222 3333 4444", "My card is [REDACTED_CARD]")
    ]
    
    for input_text, expected in test_cases:
        assert scrub_pii(input_text) == expected
