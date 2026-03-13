from app.workflows.state import GraphState
from langchain_core.messages import ToolMessage
from app.connectors.mcp.client import call_mcp_tool
import app.connectors.local_tools as local_tools
import json
import logging

logger = logging.getLogger("tools_execution")

# Map of tool names that reside locally vs MCP
LOCAL_TOOL_REGISTRY = {
    "update_user_profile": local_tools.update_user_profile,
    "get_current_time": local_tools.get_current_time,
    "read_local_file": local_tools.read_local_file,
    "write_local_file": local_tools.write_local_file,
    "list_local_directory": local_tools.list_local_directory,
}

async def execute_tools(state: GraphState) -> dict:
    """
    Unified Tool Execution Node.
    Distinguishes between local Python tools and external MCP tools.
    """
    messages = state.get("messages", [])
    if not messages:
        return {"messages": []}
        
    last_msg = messages[-1]
    if not hasattr(last_msg, "tool_calls") or not last_msg.tool_calls:
        return {"messages": []}
        
    responses = []
    user_id = state.get("user_id")
    
    for tool_call in last_msg.tool_calls:
        tool_name = tool_call["name"]
        args = tool_call["args"]
        tool_call_id = tool_call.get("id", "")
        
        logger.info(f"Executing tool: {tool_name}")
        
        # 1. Check Local Registry
        if tool_name in LOCAL_TOOL_REGISTRY:
            try:
                # Local tools might need user_id as a positional arg if defined that way
                if tool_name == "update_user_profile":
                    result = await LOCAL_TOOL_REGISTRY[tool_name](user_id, args)
                else:
                    result = await LOCAL_TOOL_REGISTRY[tool_name](**args)
            except Exception as e:
                logger.error(f"Local tool {tool_name} failed: {e}")
                result = {"error": str(e)}
        
        # 2. Default to Unified MCP Client
        else:
            result = await call_mcp_tool(tool_name, args)
            
        responses.append(ToolMessage(
            content=json.dumps(result), 
            name=tool_name, 
            tool_call_id=tool_call_id
        ))

    return {"messages": responses}
