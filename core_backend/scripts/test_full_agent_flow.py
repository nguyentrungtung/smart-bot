import asyncio
import logging
import json
import sys
from unittest.mock import AsyncMock, patch, MagicMock

# --- 0. MOCK HEAVY MODULES BEFORE IMPORTS ---
# This prevents the app from trying to connect to a real DB during import
mock_app = MagicMock()
mock_app.state = MagicMock()
mock_app.state.pool = AsyncMock()

# Stub out the modules that cause circular or DB-heavy imports
sys.modules["app.main"] = MagicMock()
sys.modules["app.main"].app = mock_app

# Now we can safely import everything else
from langchain_core.messages import HumanMessage, AIMessage, ToolMessage
from app.workflows.graph import agent_graph
from app.workflows.state import GraphState

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("test_flow")

async def test_full_agent_scenarios():
    """
    Simulates multiple user scenarios to verify RAG, Tools, and Bypass logic.
    """
    print("\n=== STARTING COMPREHENSIVE E2E AGENT TESTING ===\n")

    thread_id = "test_thread_123"
    config = {"configurable": {"thread_id": thread_id}}

    # 1. Mock DB Logic in nodes
    mock_cur = MagicMock()
    mock_cur.fetchall = AsyncMock(return_value=[("ISO 9001:2015 là tiêu chuẩn về Hệ thống quản lý chất lượng...", 0.95)])
    mock_cur.execute = AsyncMock()
    
    # Mock Cursor Context Manager
    mock_cur_cm = MagicMock()
    mock_cur_cm.__aenter__ = AsyncMock(return_value=mock_cur)
    mock_cur_cm.__aexit__ = AsyncMock()
    
    mock_conn = MagicMock()
    mock_conn.cursor = MagicMock(return_value=mock_cur_cm)
    
    # Mock Connection Context Manager
    mock_conn_cm = MagicMock()
    mock_conn_cm.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_conn_cm.__aexit__ = AsyncMock()
    
    mock_pool = MagicMock()
    mock_pool.connection = MagicMock(return_value=mock_conn_cm)
    
    mock_app.state.pool = mock_pool


    # 2. Mock LiteLLM Completion
    async def mock_acompletion(*args, **kwargs):
        messages = kwargs.get("messages", [])
        
        # Check if the last message is a ToolMessage (to prevent recursion)
        if messages and messages[-1]["role"] == "tool":
            mock_resp = MagicMock()
            mock_choice = MagicMock()
            mock_msg = MagicMock()
            mock_msg.content = "Dựa trên thông tin tôi tìm được, thời tiết ở Hà Nội đang rất đẹp."
            mock_msg.tool_calls = None
            mock_choice.message = mock_msg
            mock_resp.choices = [mock_choice]
            return mock_resp

        # Find the last HumanMessage
        last_msg = ""
        for m in reversed(messages):
            if m["role"] == "user":
                last_msg = m["content"]
                break

        
        # Scenario: Weather
        if "thời tiết" in last_msg.lower():
            mock_resp = MagicMock()
            mock_choice = MagicMock()
            mock_msg = MagicMock()
            mock_msg.content = "Tôi đang kiểm tra thời tiết."
            tool_call = MagicMock()
            tool_call.id = "call_weather_1"
            tool_call.function.name = "get_weather"
            tool_call.function.arguments = json.dumps({"location": "Hà Nội"})
            mock_msg.tool_calls = [tool_call]
            mock_choice.message = mock_msg
            mock_resp.choices = [mock_choice]
            return mock_resp
            
        # Scenario: ISO (RAG)
        elif "iso 9001" in last_msg.lower():
            mock_resp = MagicMock()
            mock_choice = MagicMock()
            mock_msg = MagicMock()
            mock_msg.content = "Theo tài liệu ISO 9001:2015, đây là tiêu chuẩn quốc tế về quản lý chất lượng."
            mock_msg.tool_calls = None
            mock_choice.message = mock_msg
            mock_resp.choices = [mock_choice]
            return mock_resp
            
        # Scenario: Normal Text
        else:
            mock_resp = MagicMock()
            mock_choice = MagicMock()
            mock_msg = MagicMock()
            mock_msg.content = "Tôi có thể giúp gì thêm không?"
            mock_msg.tool_calls = None
            mock_choice.message = mock_msg
            mock_resp.choices = [mock_choice]
            return mock_resp

    # Apply patches
    with patch("litellm.acompletion", side_effect=mock_acompletion):
        with patch("app.memory.long_term.LongTermMemory.get_profile", return_value={"name": "Tùng"}):
            
            # --- CASE 1: RAG FLOW (ISO 9001) ---
            print("\n[Case 1] RAG Search: 'ISO 9001 là gì?'")
            input_state = {"messages": [HumanMessage(content="ISO 9001 là gì?")]}
            
            # Reset mock results for RAG
            mock_cur.fetchall.return_value = [("ISO 9001:2015 là tiêu chuẩn về Hệ thống quản lý chất lượng...", 0.95)]
            
            output = await agent_graph.ainvoke(input_state, config=config)
            final_msg = output["messages"][-1].content
            print(f"Agent Response: {final_msg}")
            assert "ISO 900" in final_msg

            # --- CASE 2: TOOL FLOW (Weather) ---
            print("\n[Case 2] Tool Calling: 'Thời tiết Hà Nội hôm nay thế nào?'")
            input_state_tool = {"messages": [HumanMessage(content="Thời tiết Hà Nội hôm nay thế nào?")]}
            
            output_tool = await agent_graph.ainvoke(input_state_tool, config=config)
            
            msg_types = [type(m).__name__ for m in output_tool["messages"]]
            print(f"Message Chain: {msg_types}")
            assert "ToolMessage" in msg_types
            
            # Final response should contain weather info
            final_resp = output_tool["messages"][-1].content
            print(f"Final Agent Response: {final_resp}")

            # --- CASE 3: BYPASS FLOW (Off-Topic) ---
            print("\n[Case 3] Bypass (No RAG, No Tool): 'Kể truyện cười'")
            # Return empty for RAG
            mock_cur.fetchall.return_value = []
            
            input_state_bypass = {"messages": [HumanMessage(content="Kể truyện cười")]}
            # We must expect the graph to finish with the fallback message
            output_bypass = await agent_graph.ainvoke(input_state_bypass, config=config)
            
            bypass_msg = output_bypass["messages"][-1].content
            print(f"Agent Response: {bypass_msg}")
            assert "Xin lỗi, tôi chưa rõ tài liệu này" in bypass_msg

    print("\n=== ALL E2E FLOW TESTS PASSED! ===\n")

if __name__ == "__main__":
    asyncio.run(test_full_agent_scenarios())
