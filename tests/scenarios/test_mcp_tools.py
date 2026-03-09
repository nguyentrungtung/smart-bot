import pytest
from unittest.mock import AsyncMock, patch

from core_backend.app.workflows.graph import agent_graph # Assuming actual graph compiles here
from langchain_core.messages import HumanMessage
from langchain_core.messages import ToolMessage

@pytest.fixture
def mock_weather_mcp():
    """Mock the external Open-Meteo tool response to simulate MCP"""
    return {
        "temperature": 25.5,
        "location": "Hanoi",
        "condition": "Sunny"
    }

@pytest.fixture
def mock_time_mcp():
    """Mock a datetime returned by basic_tools server"""
    return {
        "current_time": "2026-03-09T09:30:00+07:00",
        "timezone": "Asia/Ho_Chi_Minh"
    }

@pytest.mark.asyncio
async def test_weather_mcp_routing(mock_weather_mcp):
    """Ensure the user's query about weather triggers the right tool"""
    
    user_input = HumanMessage(content="Thời tiết Hà Nội hôm nay thế nào?")
    
    # Mocking the LiteLLM response to natively select the get_weather tool
    mock_llm_response = AsyncMock()
    mock_llm_response.tool_calls = [{"name": "get_weather", "args": {"location": "Hanoi"}}]
    
    with patch("core_backend.app.workflows.nodes.generate.llm.ainvoke", return_value=mock_llm_response):
        with patch("core_backend.app.mcp_clients.basic_tools.get_weather", return_value=mock_weather_mcp):
            
            # The agent graph receives the message, routes to tool, grabs data and generates the final text
            result_state = await agent_graph.ainvoke({"messages": [user_input]})
    
            # Should have the ToolMessage in history containing the JSON mock weather
            assert any(isinstance(msg, ToolMessage) and msg.name == "get_weather" for msg in result_state["messages"])
            assert '"location": "Hanoi"' in str(result_state["messages"])

@pytest.mark.asyncio
async def test_time_mcp_routing(mock_time_mcp):
    """Ensure asking for time routes to tool, not hallucinated LLM time"""
    
    user_input = HumanMessage(content="Bây giờ là mấy giờ rồi?")
    
    # Mock LiteLLM selecting the time tool
    mock_llm_response = AsyncMock()
    mock_llm_response.tool_calls = [{"name": "get_current_time", "args": {"timezone": "Asia/Ho_Chi_Minh"}}]
    
    with patch("core_backend.app.workflows.nodes.generate.llm.ainvoke", return_value=mock_llm_response):
        with patch("core_backend.app.mcp_clients.basic_tools.get_current_time", return_value=mock_time_mcp):
            
            result_state = await agent_graph.ainvoke({"messages": [user_input]})
            
            tool_msg = next((msg for msg in result_state["messages"] if isinstance(msg, ToolMessage)), None)
            
            assert tool_msg is not None
            assert tool_msg.name == "get_current_time"
            assert "2026-03-09" in tool_msg.content
