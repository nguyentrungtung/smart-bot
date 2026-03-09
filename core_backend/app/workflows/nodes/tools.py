from app.workflows.state import GraphState
from langchain_core.messages import ToolMessage
import app.mcp_clients.basic_tools as basic_tools
import json

async def execute_tools(state: GraphState) -> dict:
    """
    Parses the last AI message. If it requested a tool (like Weather or Time),
    calls the respective MCP Client.
    """
    messages = state.get("messages", [])
    if not messages:
        return {"messages": []}
        
    last_msg = messages[-1]
    
    # Check if the AI model output explicit tool_calls
    if not hasattr(last_msg, "tool_calls") or not last_msg.tool_calls:
        return {"messages": []}
        
    responses = []
    
    for tool_call in last_msg.tool_calls:
        tool_name = tool_call["name"]
        args = tool_call["args"]
        
        # Simple dynamic router
        if tool_name == "get_weather":
            result = await basic_tools.get_weather(**args)
            responses.append(ToolMessage(content=json.dumps(result), name=tool_name, tool_call_id=tool_call.get("id", "")))
            
        elif tool_name == "get_current_time":
            result = await basic_tools.get_current_time(**args)
            responses.append(ToolMessage(content=json.dumps(result), name=tool_name, tool_call_id=tool_call.get("id", "")))

    return {"messages": responses}
