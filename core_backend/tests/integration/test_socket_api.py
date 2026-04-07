import pytest
import asyncio
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch
from app.api.socket_handler import handle_message, connect as handle_connect


@pytest.fixture
def mock_sio():
    """Patch sio with an AsyncMock so await sio.emit(...) works."""
    with patch("app.api.socket_handler.sio") as mock:
        mock.emit = AsyncMock()
        # session() must be an async context manager yielding a dict
        @asynccontextmanager
        async def _session(sid):
            yield {}
        mock.session = _session
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
        assert await handle_connect(sid, environ, {"token": "valid"}) is True


@pytest.mark.asyncio
async def test_socket_message_locking(mock_sio):
    """Test that message handling enforces Redis session locking."""
    lock_params = {}

    # Build a mock redis client whose .lock() returns an awaitable-acquire mock
    mock_lock_obj = MagicMock()
    mock_lock_obj.acquire = AsyncMock(return_value=True)
    mock_lock_obj.release = AsyncMock()

    mock_redis_client = AsyncMock()
    mock_redis_client.lock = MagicMock(return_value=mock_lock_obj)

    # Capture lock() call args for assertion
    original_lock = mock_redis_client.lock
    def capturing_lock(key, timeout, blocking_timeout):
        lock_params["key"] = key
        lock_params["timeout"] = timeout
        return mock_lock_obj
    mock_redis_client.lock = capturing_lock

    with patch("app.api.socket_handler.get_redis", new=AsyncMock(return_value=mock_redis_client)):
        data = {"session_id": "sess_1", "content": "hello"}

        # Prevent the graph from actually running
        with patch("app.api.socket_handler.get_agent_graph", return_value=AsyncMock()):
            with patch("app.api.socket_handler.ChatHistoryTracker") as mock_tracker_cls:
                mock_tracker = AsyncMock()
                mock_tracker.ensure_session_exists = AsyncMock()
                mock_tracker.log_interaction = AsyncMock(return_value="iid_1")
                mock_tracker_cls.return_value = mock_tracker
                with patch("app.api.socket_handler.get_pool", return_value=MagicMock()):
                    with patch("app.api.socket_handler.scrub_pii", side_effect=lambda x: x):
                        with patch("app.api.socket_handler.MultimodalProcessor") as mock_mm:
                            # format_message_content is now async — must return a coroutine
                            mock_mm.format_message_content = AsyncMock(return_value="hello")
                            with patch("app.api.socket_handler.get_capabilities", return_value={}):
                                with patch("app.utils.tokens.calculate_tokens", return_value=10):
                                    with patch("app.api.socket_handler.session_id_context"):
                                        with patch("app.api.socket_handler.interaction_id_context"):
                                            await handle_message("sid_1", data)

    assert lock_params.get("key") == "lock:sess_1"
    assert lock_params.get("timeout") == 120
