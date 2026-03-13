import pytest
import json
from unittest.mock import AsyncMock, patch
from langchain_core.messages import HumanMessage, ToolMessage, AIMessage
from app.workflows.graph import get_agent_graph

@pytest.fixture
def agent_graph():
    return get_agent_graph()

@pytest.mark.asyncio
async def test_workflow_local_tool_routing(agent_graph):
    """Test routing to a local tool (get_current_time)."""
    user_msg = HumanMessage(content="Mấy giờ rồi?")
    
    # 1. Mock LLM choosing the tool
    mock_resp_tool = AsyncMock()
    mock_resp_tool.tool_calls = [{
        "name": "get_current_time", 
        "args": {"timezone": "Asia/Ho_Chi_Minh"}, 
        "id": "call_123",
        "type": "tool_call"
    }]
    mock_resp_tool.content = ""

    # 2. Mock LLM generating final answer after tool
    mock_resp_final = AsyncMock()
    mock_resp_final.tool_calls = []
    mock_resp_final.content = "Bây giờ là 10 giờ sáng."

    with patch("app.workflows.nodes.generate.llm.ainvoke", side_effect=[mock_resp_tool, mock_resp_final]):
        # Mock the local tool directly
        with patch("app.connectors.local_tools.get_current_time", return_value={"status": "success", "current_time": "10:00"}):
            result = await agent_graph.ainvoke({"messages": [user_msg]})
            
            # Verify tool output in messages
            messages = result["messages"]
            assert any(isinstance(m, ToolMessage) and m.name == "get_current_time" for m in messages)
            assert "10:00" in str(messages)
            assert "10 giờ sáng" in messages[-1].content

@pytest.mark.asyncio
async def test_workflow_mcp_tool_resilience(agent_graph):
    """Test routing to MCP tool with the resilience client (circuit breaker)."""
    user_msg = HumanMessage(content="Tạo giúp tôi một website Xweb.")
    
    mock_resp_tool = AsyncMock()
    mock_resp_tool.tool_calls = [{
        "name": "create_xweb_instance", 
        "args": {"name": "test-site"}, 
        "id": "call_mcp_1",
        "type": "tool_call"
    }]
    
    with patch("app.workflows.nodes.generate.llm.ainvoke", return_value=mock_resp_tool):
        # Mock call_mcp_tool to simulate a failure (trip circuit breaker)
        with patch("app.connectors.mcp.client.call_mcp_tool", return_value={"status": "error", "message": "Circuit breaker open"}):
            result = await agent_graph.ainvoke({"messages": [user_msg]})
            
            messages = result["messages"]
            # Verify the error message from the circuit breaker is injected
            assert any(isinstance(m, ToolMessage) and "Circuit breaker open" in m.content for m in messages)

@pytest.mark.asyncio
async def test_workflow_rag_confidence_fallback(agent_graph):
    """Test RAG fallback when no documents match confidence threshold."""
    user_msg = HumanMessage(content="Bạn nghĩ gì về chính trị thế giới?")
    
    # Mock RAG search to return nothing (empty list)
    with patch("app.workflows.nodes.rag_search.rag_search", return_value={"rag_documents": [], "metadata": {"rag_failed": True}}):
        result = await agent_graph.ainvoke({"messages": [user_msg]})
        
        # Should hit the fallback guard
        assert "Xin lỗi, tôi chưa rõ tài liệu này" in result["messages"][-1].content
