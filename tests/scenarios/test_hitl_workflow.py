import pytest
from unittest.mock import AsyncMock, patch

from app.workflows.graph import workflow  # We need to compile it with memorysaver to test interruptions
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

@pytest.mark.asyncio
async def test_xweb_hitl_interruption(memory, mock_xweb_mcp):
    """
    Ensure the user's request to create an xweb instance successfully routing to the HITL interruption node.
    """
    # Compile the graph explicitly with the memory saver to enable breakpoints
    test_graph = workflow.compile(checkpointer=memory, interrupt_before=["xweb_tool"])
    
    config = {"configurable": {"thread_id": "test_hitl_thread_1"}}
    
    user_input = HumanMessage(content="Tạo cho tôi một trang web bán hàng")
    
    # Mocking LiteLLM to select create_xweb_instance via AIMessage standard format
    mock_llm_msg1 = AIMessage(
        content="", 
        tool_calls=[{"name": "create_xweb_instance", "args": {"business_type": "ecommerce", "theme_color": "blue", "admin_email": "admin@test.com"}, "id": "mock_tool_1"}]
    )
    
    mock_llm_msg2 = AIMessage(content="Trang web của bạn đã được tạo thành công!")
    
    with patch("app.workflows.nodes.generate.llm.ainvoke", side_effect=[mock_llm_msg1, mock_llm_msg2]):
        with patch("app.mcp_clients.xweb_tool.create_xweb_instance", return_value=mock_xweb_mcp):
            
            # Step 1: Initial invocation should hit the interrupt_before="xweb_tool"
            # It will pause execution and return the current state before executing the xweb tool
            result_state = await test_graph.ainvoke({"messages": [user_input]}, config)
            
            # Verify the graph is indeed paused/interrupted
            state_snapshot = test_graph.get_state(config)
            assert state_snapshot.next == ("xweb_tool",) , "Graph should be paused exactly before xweb_tool"
            
            # Step 2: Now we simulate the REST API Webhook approval, which simply resumes the graph
            # by invoking it again with None (meaning proceed with current state)
            final_state = await test_graph.ainvoke(None, config)
            
            # Verify the final state contains the tool message and final response
            messages = final_state["messages"]
            
            # Assert the tool was executed
            assert any(isinstance(msg, ToolMessage) and msg.name == "create_xweb_instance" for msg in messages)
            
            # Assert the final text contains success
            assert "Trang" in messages[-1].content
