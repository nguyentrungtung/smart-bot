import pytest
import json
from unittest.mock import AsyncMock, MagicMock, patch
from langchain_core.messages import HumanMessage, ToolMessage, AIMessage
from app.workflows.graph import get_agent_graph


@pytest.fixture
def agent_graph():
    return get_agent_graph()


def _make_stream_chunk(content: str = "", tool_calls=None):
    """Build a minimal litellm streaming chunk mock."""
    chunk = MagicMock()
    delta = MagicMock()
    delta.content = content
    delta.tool_calls = tool_calls
    delta.reasoning_content = None
    chunk.choices = [MagicMock(delta=delta)]
    chunk.usage = None
    return chunk


def _make_async_stream(*chunks):
    """Return an async generator that yields mock chunks."""
    async def _gen():
        for c in chunks:
            yield c
    return _gen()


@pytest.mark.asyncio
async def test_workflow_local_tool_routing(agent_graph):
    """Test routing to a local tool (get_current_time)."""
    user_msg = HumanMessage(content="Mấy giờ rồi?")

    # First LLM call: returns a tool call chunk
    tool_call_delta = MagicMock()
    tool_call_delta.index = 0
    tool_call_delta.id = "call_123"
    tool_call_delta.function = MagicMock(name="get_current_time", arguments='{"timezone":"Asia/Ho_Chi_Minh"}')
    tool_call_delta.function.name = "get_current_time"
    tool_call_delta.function.arguments = '{"timezone":"Asia/Ho_Chi_Minh"}'

    chunk_with_tool = _make_stream_chunk(tool_calls=[tool_call_delta])
    # Final LLM call: plain text answer
    chunk_final = _make_stream_chunk(content="Bây giờ là 10 giờ sáng.")

    call_count = 0

    async def mock_acompletion(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return _make_async_stream(chunk_with_tool)
        return _make_async_stream(chunk_final)

    mock_tool_fn = AsyncMock(return_value={"status": "success", "current_time": "10:00"})

    with patch("app.workflows.nodes.generate.litellm.acompletion", side_effect=mock_acompletion):
        # Patch the registry entry directly — function references are captured at import
        with patch.dict("app.workflows.nodes.tools.LOCAL_TOOL_REGISTRY",
                        {"get_current_time": mock_tool_fn}):
            result = await agent_graph.ainvoke({"messages": [user_msg]})

    messages = result["messages"]
    assert any(isinstance(m, ToolMessage) and m.name == "get_current_time" for m in messages)
    tool_msg = next(m for m in messages if isinstance(m, ToolMessage) and m.name == "get_current_time")
    assert "10:00" in tool_msg.content


@pytest.mark.asyncio
async def test_workflow_mcp_tool_resilience(agent_graph):
    """Test routing to MCP tool with circuit breaker error surfaced in ToolMessage.
    Uses get_weather (non-HITL) to avoid the interrupt_before=["sensitive_tools"] pause.
    """
    user_msg = HumanMessage(content="Thời tiết Hà Nội hôm nay thế nào?")

    tool_call_delta = MagicMock()
    tool_call_delta.index = 0
    tool_call_delta.id = "call_mcp_1"
    tool_call_delta.function = MagicMock()
    tool_call_delta.function.name = "get_weather"
    tool_call_delta.function.arguments = '{"location":"Hà Nội"}'

    chunk_tool = _make_stream_chunk(tool_calls=[tool_call_delta])
    chunk_final = _make_stream_chunk(content="Đã xử lý yêu cầu.")

    call_count = 0

    async def mock_acompletion(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return _make_async_stream(chunk_tool)
        return _make_async_stream(chunk_final)

    with patch("app.workflows.nodes.generate.litellm.acompletion", side_effect=mock_acompletion):
        # Patch call_mcp_tool where tools.py imported it
        with patch("app.workflows.nodes.tools.call_mcp_tool", new=AsyncMock(
            return_value={"status": "error", "message": "Circuit breaker open"}
        )):
            result = await agent_graph.ainvoke({"messages": [user_msg]})

    messages = result["messages"]
    assert any(
        isinstance(m, ToolMessage) and "Circuit breaker open" in m.content
        for m in messages
    )


@pytest.mark.asyncio
async def test_workflow_rag_confidence_fallback(agent_graph):
    """Test that RAG failure is handled and generation still proceeds."""
    user_msg = HumanMessage(content="Bạn nghĩ gì về chính trị thế giới?")

    chunk_final = _make_stream_chunk(content="Xin lỗi, tôi chưa rõ tài liệu này")

    async def mock_acompletion(*args, **kwargs):
        return _make_async_stream(chunk_final)

    # Patch rag_search at the graph module level (where it was imported)
    with patch("app.workflows.graph.rag_search", new=AsyncMock(
        return_value={"rag_documents": [], "metadata": {"rag_failed": True}}
    )):
        with patch("app.workflows.nodes.generate.litellm.acompletion", side_effect=mock_acompletion):
            result = await agent_graph.ainvoke({"messages": [user_msg]})

    assert result["messages"][-1].content != ""
