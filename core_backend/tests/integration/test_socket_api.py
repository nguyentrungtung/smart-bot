import pytest
import asyncio
from unittest.mock import AsyncMock, patch
from app.api.socket_handler import handle_message, connect as handle_connect

@pytest.fixture
def mock_sio():
    with patch("app.api.socket_handler.sio") as mock:
        yield mock

@pytest.mark.asyncio
async def test_socket_auth_handshake(mock_sio):
    """Test that connection requires a valid token in auth payload."""
    sid = "sid_1"
    environ = {"REMOTE_ADDR": "127.0.0.1"}
    
    # Fail without token
    assert await handle_connect(sid, environ, {}) is False
    
    # Success with valid mock token
    with patch("app.api.socket_handler.verify_jwt_token", return_value={"sub": "user1"}):
        from contextlib import asynccontextmanager
        @asynccontextmanager
        async def mock_session(sid): yield {}
        
        with patch("app.api.socket_handler.sio.session", side_effect=mock_session):
            assert await handle_connect(sid, environ, {"token": "valid"}) is True

@pytest.mark.asyncio
async def test_socket_message_locking(mock_sio):
    """Test that message handling enforces Redis session locking."""
    from contextlib import asynccontextmanager
    
    lock_params = {}
    @asynccontextmanager
    async def mock_lock(key, timeout, blocking_timeout):
        lock_params["key"] = key
        lock_params["timeout"] = timeout
        yield True

    with patch("app.api.socket_handler.get_redis") as mock_redis:
        mock_redis.return_value.lock = mock_lock
        
        # Mock handle_message dependencies
        data = {"session_id": "sess_1", "content": "hello"}
        
        # We don't want to run the whole graph here, just test the lock wrap
        with patch("app.api.socket_handler.get_agent_graph", return_value=AsyncMock()):
             await handle_message("sid_1", data)
             
             assert lock_params["key"] == "lock:sess_1"
             assert lock_params["timeout"] == 30
