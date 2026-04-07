import json
import logging
from app.workflows.state import GraphState
from langchain_core.messages import ToolMessage, AIMessage
from app.connectors.mcp.client import call_mcp_tool
import app.connectors.local_tools as local_tools

logger = logging.getLogger("tools_execution")

# Map of tool names that reside locally vs MCP
LOCAL_TOOL_REGISTRY = {
    "update_user_profile": local_tools.update_user_profile,
    "get_current_time": local_tools.get_current_time,
    "read_local_file": local_tools.read_local_file,
    "write_local_file": local_tools.write_local_file,
    "list_local_directory": local_tools.list_local_directory,
}

# Build allowlist from tool definitions exposed to the LLM.
# Any tool_name not in this set is rejected before execution.
try:
    from app.workflows.nodes.tool_defs import TOOLS as _TOOL_DEFS
    _ALLOWED_TOOLS: frozenset[str] = frozenset(
        t["function"]["name"] for t in _TOOL_DEFS
    )
except Exception:
    _ALLOWED_TOOLS = frozenset(LOCAL_TOOL_REGISTRY.keys())


def _build_already_called_cache(messages: list) -> dict:
    """
    Scan message history for ToolMessages in this turn to build a dedup cache.
    Key: (tool_name, frozen_args) → result JSON string.
    This prevents the same tool+args from being called twice in one turn
    when the LLM redundantly generates duplicate tool_calls.
    """
    cache: dict[tuple, str] = {}
    for msg in reversed(messages):
        # Stop scanning once we pass the last AIMessage with tool_calls
        if isinstance(msg, AIMessage):
            break
        if isinstance(msg, ToolMessage):
            try:
                key = (msg.name, msg.content)  # content is already the result
                cache[(msg.name, msg.tool_call_id)] = msg.content
            except Exception:
                pass
    return cache


async def execute_tools(state: GraphState) -> dict:
    """
    Unified Tool Execution Node.
    - Routes to local registry or MCP client.
    - Deduplicates: skips tool+args already called this turn (returns cached result).
    - Counts each individual MCP/local call toward tool_call_count (not per execute_tools invocation).
    """
    messages = state.get("messages", [])
    if not messages:
        return {"messages": []}

    last_msg = messages[-1]
    if not hasattr(last_msg, "tool_calls") or not last_msg.tool_calls:
        return {"messages": []}

    responses = []
    user_id = state.get("user_id")
    current_count = state.get("tool_call_count", 0)

    # Track (name, frozen_args_json) seen THIS execute_tools call to dedup
    # duplicate tool_calls in the same AIMessage response
    seen_this_call: set[tuple] = set()

    for tool_call in last_msg.tool_calls:
        tool_name = tool_call["name"]
        args = tool_call["args"]
        tool_call_id = tool_call.get("id", "")
        args_key = json.dumps(args, sort_keys=True)
        dedup_key = (tool_name, args_key)

        # Skip duplicate tool+args within the same response
        if dedup_key in seen_this_call:
            logger.warning(
                f"DEDUP: Skipping duplicate tool call {tool_name}({args_key}) "
                f"already called this response."
            )
            responses.append(ToolMessage(
                content=json.dumps({"note": "Duplicate call skipped — result same as previous."}),
                name=tool_name,
                tool_call_id=tool_call_id,
            ))
            continue

        # Reject tools not in the allowlist (defense-in-depth against prompt injection)
        if tool_name not in _ALLOWED_TOOLS:
            logger.error(f"SECURITY: Rejected unknown tool '{tool_name}' — not in allowlist")
            responses.append(ToolMessage(
                content=json.dumps({"error": f"Tool '{tool_name}' is not permitted."}),
                name=tool_name,
                tool_call_id=tool_call_id,
            ))
            continue

        seen_this_call.add(dedup_key)
        current_count += 1  # Count each individual call

        logger.info(f"Executing tool [{current_count}]: {tool_name}({args_key[:60]})")

        # 1. Check Local Registry
        if tool_name in LOCAL_TOOL_REGISTRY:
            try:
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
            tool_call_id=tool_call_id,
        ))

    return {"messages": responses, "tool_call_count": current_count}
