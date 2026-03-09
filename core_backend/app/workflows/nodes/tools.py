from app.workflows.state import GraphState
from langchain_core.messages import ToolMessage
import app.mcp_clients.basic_tools as basic_tools
import app.mcp_clients.xweb_tool as xweb_mcp
from app.workflows.hitl import request_human_approval
import json

async def execute_basic_tools(state: GraphState) -> dict:
    """
    Executes standard tools like weather and time that do NOT require human approval.
    """
    messages = state.get("messages", [])
    if not messages:
        return {"messages": []}
        
    last_msg = messages[-1]
    if not hasattr(last_msg, "tool_calls") or not last_msg.tool_calls:
        return {"messages": []}
        
    responses = []
    
    for tool_call in last_msg.tool_calls:
        tool_name = tool_call["name"]
        args = tool_call["args"]
        
        if tool_name == "get_weather":
            result = await basic_tools.get_weather(**args)
            responses.append(ToolMessage(content=json.dumps(result), name=tool_name, tool_call_id=tool_call.get("id", "")))
            
        elif tool_name == "get_current_time":
            result = await basic_tools.get_current_time(**args)
            responses.append(ToolMessage(content=json.dumps(result), name=tool_name, tool_call_id=tool_call.get("id", "")))

    return {"messages": responses}

async def execute_xweb_tool(state: GraphState) -> dict:
    """
    Executes the high-risk Xweb Provisioning tool.
    This node is meant to be interrupted BEFORE execution by LangGraph for HITL approval.
    """
    messages = state.get("messages", [])
    if not messages:
        return {"messages": []}
        
    last_msg = messages[-1]
    if not hasattr(last_msg, "tool_calls") or not last_msg.tool_calls:
        return {"messages": []}
        
    responses = []
    
    for tool_call in last_msg.tool_calls:
        tool_name = tool_call["name"]
        args = tool_call["args"]
        
        if tool_name == "create_xweb_instance":
            # Call the MCP Client with Circuit Breaker
            result = await xweb_mcp.create_xweb_instance(**args)
            responses.append(ToolMessage(content=json.dumps(result), name=tool_name, tool_call_id=tool_call.get("id", "")))

    return {"messages": responses}

