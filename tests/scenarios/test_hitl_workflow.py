import pytest
import json
from unittest.mock import AsyncMock, patch, MagicMock
from app.workflows.graph import workflow 
from langchain_core.messages import HumanMessage, ToolMessage, AIMessage
from langgraph.checkpoint.memory import MemorySaver

@pytest.fixture
def memory():
    """Returns an in-memory checkpointer required for testing graph interruptions"""
    return MemorySaver()

@pytest.fixture
def mock_xweb_mcp():
    """Mock the external Xweb MCP response"""
    return {
        "status": "success",
        "result": "https://test-business-abcdef.company-xweb.com"
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
        # For simplicity in testing, we just yield one chunk with the whole tool call
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
async def test_xweb_hitl_interruption(memory, mock_xweb_mcp):
    """
    Ensure the user's request to create an xweb instance successfully routing to the HITL interruption node.
    """
    # Compile the graph explicitly with the memory saver to enable breakpoints
    test_graph = workflow.compile(checkpointer=memory, interrupt_before=["xweb_tool"])
    
    config = {"configurable": {"thread_id": "test_hitl_thread_1"}}
    
    # Use keywords that trigger the tool bypass in generate.py
    user_input = HumanMessage(content="Tạo xweb cho tôi")
    
    # Mock LiteLLM Completion responses
    tool_calls = [{"name": "create_xweb_instance", "args": {"business_type": "ecommerce", "theme_color": "blue", "admin_email": "admin@test.com"}}]
    
    stream1 = make_mock_stream(tool_calls=tool_calls)
    stream2 = make_mock_stream(content="Trang web của bạn đã được tạo thành công!")
    
    # We patch litellm.acompletion in the generate node module
    with patch("app.workflows.nodes.generate.litellm.acompletion", side_effect=[stream1, stream2]):
        with patch("app.mcp_clients.xweb_tool.create_xweb_instance", return_value=mock_xweb_mcp):
            # Seed the pool as None so nodes don't crash if they try to use it
            with patch("app.utils.db.pool", None):
                # We need to skip rag_search or mock it
                with patch("app.workflows.nodes.rag_search.rag_search", return_value={"rag_documents": ["docs"]}):
                    with patch("app.workflows.nodes.fetch_profile.fetch_profile", return_value={"metadata": {"profile": {}}}):
                        with patch("app.workflows.nodes.profile_analyzer.profile_analyzer", return_value={}):

                            # Step 1: Initial invocation should hit the interrupt_before="xweb_tool"
                            # We provide thread_id so checkpoints work
                            result = await test_graph.ainvoke({
                                "messages": [user_input],
                                "user_id": "test_user",
                                "session_id": "session_1",
                                "metadata": {}
                            }, config)
                            
                            # Verify the graph is indeed paused/interrupted
                            state_snapshot = test_graph.get_state(config)
                            assert "xweb_tool" in state_snapshot.next, f"Graph should be paused before xweb_tool, but next is {state_snapshot.next}"
                            
                            # Step 2: Resume
                            final_state = await test_graph.ainvoke(None, config)
                            
                            # Verify final state
                            messages = final_state["messages"]
                            assert any(isinstance(msg, ToolMessage) for msg in messages)
                            assert "Trang" in messages[-1].content
