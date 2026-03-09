import pytest
import asyncio
from unittest.mock import AsyncMock, patch

# Adjusted import from root
from core_backend.app.api.socket_handler import handle_message, handle_connect 

@pytest.fixture
def mock_sio():
    """Returns a mock socket.io server instance"""
    return AsyncMock()

@pytest.fixture
def mock_redis():
    """Returns a mocked redis client that skips real locking mechanics"""
    with patch("core_backend.app.api.socket_handler.redis_client") as mock:
        yield mock

@pytest.mark.asyncio
async def test_socket_connection_rejected_no_auth(mock_sio):
    """Connections must be rejected if no JWT payload found"""
    sid = "test_sid_without_auth"
    environ = {"REMOTE_ADDR": "127.0.0.1"}
    auth = None  # Missing auth payload
    
    result = await handle_connect(sid, environ, auth)
    
    assert result is False, "Socket connection should be rejected without auth payload"

@pytest.mark.asyncio
async def test_socket_connection_accepted_with_auth(mock_sio):
    """Connection accepted if mocked auth payload validates successfully"""
    sid = "test_sid_with_auth"
    environ = {"REMOTE_ADDR": "127.0.0.1"}
    auth = {"token": "VALID_MOCK_JWT"}
    
    # Needs to mock out the underlying verify_jwt_token inside handle_connect
    with patch("core_backend.app.api.socket_handler.verify_jwt_token", return_value={"sub": "user_456"}):
        result = await handle_connect(sid, environ, auth)
    
    # Implicitly allowed
    assert result is True, "Socket connection should be accepted upon valid JWT decoding"

@pytest.mark.asyncio
async def test_handle_message_session_lock(mock_sio, mock_redis):
    """Ensure the handler creates a Redis timeout lock of 30 seconds explicitly"""
    
    mock_redis.lock.return_value.__aenter__.return_value = True
    
    sid = "test_sid"
    data = {"session_id": "sid_789", "content": "Hello bot"}
    
    await handle_message(sid, data)
    
    # Verify lock key matches pattern and the strict timeout value
    mock_redis.lock.assert_called_once_with("lock:sid_789", timeout=30, blocking_timeout=2)
