import pytest
import json
from unittest.mock import AsyncMock, patch, MagicMock
from app.workflows.graph import agent_graph 
from langchain_core.messages import HumanMessage, ToolMessage, AIMessage

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

async def make_mock_stream(content="", tool_calls=None):
    """Utility to create an async generator for LiteLLM stream response"""
    class Chunk:
        def __init__(self, content=None, tool_calls=None):
            class Choice:
                def __init__(self, delta):
                    self.delta = delta
            delta = MagicMock()
            delta.content = content
            delta.tool_calls = tool_calls
            delta.reasoning_content = None
            self.choices = [Choice(delta)]
            
    if tool_calls:
        tcs = []
        for i, tc in enumerate(tool_calls):
            m_tc = MagicMock()
            m_tc.index = i
            m_tc.id = tc.get("id", f"call_{i}")
            m_tc.function.name = tc["name"]
            m_tc.function.arguments = json.dumps(tc["args"])
            tcs.append(m_tc)
        yield Chunk(tool_calls=tcs)
    else:
        yield Chunk(content=content)

@pytest.mark.asyncio
async def test_weather_mcp_routing(mock_weather_mcp):
    """Ensure the user's query about weather triggers the right tool"""
    
    user_input = HumanMessage(content="Thời tiết Hà Nội hôm nay thế nào?")
    
    # Mock LiteLLM Completion responses
    tool_calls = [{"name": "get_weather", "args": {"location": "Hanoi"}}]
    
    stream1 = make_mock_stream(tool_calls=tool_calls)
    stream2 = make_mock_stream(content="Hà Nội đang nắng.")
    
    with patch("app.workflows.nodes.generate.litellm.acompletion", side_effect=[stream1, stream2]):
        with patch("app.mcp_clients.basic_tools.get_weather", return_value=mock_weather_mcp):
             # Mock dependencies to avoid DB calls
            with patch("app.utils.db.pool", None):
                with patch("app.workflows.nodes.rag_search.rag_search", return_value={"rag_documents": ["docs"]}):
                    with patch("app.workflows.nodes.fetch_profile.fetch_profile", return_value={"metadata": {"profile": {}}}):
                        with patch("app.workflows.nodes.profile_analyzer.profile_analyzer", return_value={}):

                            result_state = await agent_graph.ainvoke({"messages": [user_input]})
                    
                            # Assertions
                            messages = result_state["messages"]
                            assert any(isinstance(msg, ToolMessage) and msg.name == "get_weather" for msg in messages)
                            assert "Hà Nội" in messages[-1].content

@pytest.mark.asyncio
async def test_time_mcp_routing(mock_time_mcp):
    """Ensure asking for time routes to tool, not hallucinated LLM time"""
    
    user_input = HumanMessage(content="Bây giờ là mấy giờ rồi?")
    
    tool_calls = [{"name": "get_current_time", "args": {"timezone": "Asia/Ho_Chi_Minh"}}]
    
    stream1 = make_mock_stream(tool_calls=tool_calls)
    stream2 = make_mock_stream(content="Bây giờ là 9 giờ 30 phút.")
    
    with patch("app.workflows.nodes.generate.litellm.acompletion", side_effect=[stream1, stream2]):
        with patch("app.mcp_clients.basic_tools.get_current_time", return_value=mock_time_mcp):
            with patch("app.utils.db.pool", None):
                with patch("app.workflows.nodes.rag_search.rag_search", return_value={"rag_documents": ["docs"]}):
                    with patch("app.workflows.nodes.fetch_profile.fetch_profile", return_value={"metadata": {"profile": {}}}):
                        with patch("app.workflows.nodes.profile_analyzer.profile_analyzer", return_value={}):

                            result_state = await agent_graph.ainvoke({"messages": [user_input]})
                            
                            messages = result_state["messages"]
                            tool_msg = next((msg for msg in messages if isinstance(msg, ToolMessage)), None)
                            
                            assert tool_msg is not None
                            assert tool_msg.name == "get_current_time"
                            assert "2026-03-09" in str(tool_msg.content)
