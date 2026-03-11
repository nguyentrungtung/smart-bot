import pytest
import asyncio
from unittest.mock import AsyncMock, patch

# Adjusted import from root
from app.api.socket_handler import handle_message, connect as handle_connect 

@pytest.fixture
def mock_sio():
    """Returns a mock socket.io server instance"""
    return AsyncMock()

@pytest.fixture
def mock_redis():
    """Returns a mocked redis client that skips real locking mechanics"""
    with patch("app.api.socket_handler.get_redis") as mock_get_redis:
        # get_redis returning the mock client
        mock_client = AsyncMock()
        mock_get_redis.return_value = mock_client
        yield mock_client

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
    
    # Mocking both JWT decoder AND the internal socketio state context manager
    from contextlib import asynccontextmanager
    
    @asynccontextmanager
    async def mock_session(sid):
        yield {} # Mock dictionary for session

    with patch("app.api.socket_handler.verify_jwt_token", return_value={"sub": "user_456"}):
        with patch("app.api.socket_handler.sio.session", side_effect=mock_session):
            result = await handle_connect(sid, environ, auth)
    
    # Implicitly allowed
    assert result is True, "Socket connection should be accepted upon valid JWT decoding"

@pytest.mark.asyncio
async def test_handle_message_session_lock(mock_sio, mock_redis):
    """Ensure the handler creates a Redis timeout lock of 30 seconds explicitly"""
    
    from contextlib import asynccontextmanager
    
    lock_called_args = {}
    
    @asynccontextmanager
    async def mock_lock(key, timeout, blocking_timeout):
        lock_called_args['key'] = key
        lock_called_args['timeout'] = timeout
        lock_called_args['blocking_timeout'] = blocking_timeout
        yield True # Acquired

    mock_redis.lock = mock_lock
    
    sid = "test_sid"
    data = {"session_id": "sid_789", "content": "Hello bot"}
    
    # We also need to mock sio.emit as it expects it
    with patch("app.api.socket_handler.sio.emit") as mock_emit:
        await handle_message(sid, data)
    
    # Verify lock key matches pattern and the strict timeout value
    assert lock_called_args.get("key") == "lock:sid_789"
    assert lock_called_args.get("timeout") == 30
    assert lock_called_args.get("blocking_timeout") == 2
