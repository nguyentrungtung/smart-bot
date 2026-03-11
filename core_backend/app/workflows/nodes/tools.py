from app.workflows.state import GraphState
from langchain_core.messages import ToolMessage
import app.connectors.mcp.basic_tools as basic_tools
import app.connectors.mcp.xweb_tool as xweb_mcp
from app.workflows.hitl import request_human_approval
from app.memory.long_term import LongTermMemory
from app.utils import db
import json
import logging

logger = logging.getLogger("tools_execution")

async def execute_basic_tools(state: GraphState) -> dict:
    """
    Executes standard tools like weather, time, and profile updates.
    Uses Python 3.10+ match-case for clean routing.
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
        
        match tool_name:
            case "get_weather":
                result = await basic_tools.get_weather(**args)
                responses.append(ToolMessage(content=json.dumps(result), name=tool_name, tool_call_id=tool_call.get("id", "")))
                
            case "get_current_time":
                result = await basic_tools.get_current_time(**args)
                responses.append(ToolMessage(content=json.dumps(result), name=tool_name, tool_call_id=tool_call.get("id", "")))

            case "update_user_profile":
                user_id = state.get("user_id")
                if user_id:
                    try:
                        ltm = LongTermMemory(db.pool)
                        # Fetch current to merge facts
                        current = await ltm.get_profile(user_id)
                        
                        name = args.get("name")
                        preferences = args.get("preferences")
                        new_facts = args.get("new_facts", [])
                        
                        profile_updates = {
                            "name": name if name else current.get("name"),
                            "preferences": {**current.get("preferences", {}), **(preferences or {})},
                            "facts": list(set(current.get("facts", []) + new_facts))[:20]
                        }
                        
                        await ltm.update_profile(user_id, profile_updates)
                        result = {"status": "success", "message": "Profile updated locally via MCP node."}
                    except Exception as e:
                        logger.error(f"Failed to update profile via tool: {e}")
                        result = {"status": "error", "message": str(e)}
                else:
                    result = {"status": "error", "message": "No user_id found in state"}
                    
                responses.append(ToolMessage(content=json.dumps(result), name=tool_name, tool_call_id=tool_call.get("id", "")))

            case _:
                logger.warning(f"Tool execution: Unknown tool '{tool_name}' encountered in basic_tools node.")
                responses.append(ToolMessage(content="Tool not found in basic registry", name=tool_name, tool_call_id=tool_call.get("id", "")))

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

