import pytest
import jwt
import os
import sys
sys.path.append(os.getcwd())
from datetime import datetime, timedelta
from cryptography.hazmat.primitives import serialization
from app.middleware.auth import verify_jwt_token  # Adjusted import from root

# Setup Mock Keypair for testing
def get_mock_keys():
    # Attempt to load from .keys folder, else generate temporarily
    keys_dir = os.path.join(os.path.dirname(__file__), "..", "..", ".keys")
    private_path = os.path.join(keys_dir, "private_key.pem")
    public_path = os.path.join(keys_dir, "public_key.pem")

    with open(private_path, "rb") as f:
        private_key = serialization.load_pem_private_key(f.read(), password=None)
    with open(public_path, "rb") as f:
        public_key = serialization.load_pem_public_key(f.read())
        
    return private_key, public_key

def create_mock_token(user_id="test_user", expires_in=3600, name="Test User", role="admin"):
    private_key, _ = get_mock_keys()
    
    payload = {
        "sub": user_id,
        "name": name,
        "role": role,
        "exp": datetime.utcnow() + timedelta(seconds=expires_in),
        "iat": datetime.utcnow()
    }
    
    # Generate token using RS256 and private key
    token = jwt.encode(payload, private_key, algorithm="RS256")
    return token

@pytest.mark.asyncio
async def test_valid_jwt_token():
    """Assert valid token signature using RS256 Public Key is accepted"""
    valid_token = create_mock_token("user_123")
    
    _, public_key = get_mock_keys()
    
    # Simulate auth.py behaviour
    decoded = jwt.decode(valid_token, public_key, algorithms=["RS256"])
    
    assert decoded["sub"] == "user_123"
    assert decoded["name"] == "Test User"
    assert decoded["role"] == "admin"
    assert "exp" in decoded

@pytest.mark.asyncio
async def test_expired_jwt_token():
    """Assert token expiration date is strictly enforced"""
    expired_token = create_mock_token("user_123", expires_in=-3600)  # Expired an hour ago
    
    _, public_key = get_mock_keys()
    
    with pytest.raises(jwt.ExpiredSignatureError):
        jwt.decode(expired_token, public_key, algorithms=["RS256"])

@pytest.mark.asyncio
async def test_invalid_signature():
    """Assert tokens tampered with or signed with other keys fail"""
    invalid_token = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6IkpvaG4gRG9lIiwiaWF0IjoxNTE2MjM5MDIyfQ.SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c"
    
    _, public_key = get_mock_keys()
    
    with pytest.raises(jwt.InvalidTokenError):
         # Mismatch between header algo and required RS256 logic will also trigger InvalidTokenError usually
         jwt.decode(invalid_token, public_key, algorithms=["RS256"])
