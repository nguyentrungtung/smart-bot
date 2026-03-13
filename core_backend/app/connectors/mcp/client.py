import httpx
import logging
import json
import asyncio
from typing import Dict, Any, Optional
from app.config.settings import settings
from app.utils.resilience import get_circuit_breaker

logger = logging.getLogger(__name__)

# Resilience Circuit Breaker for all MCP external calls
mcp_circuit = get_circuit_breaker(
    name="mcp_resilience_client", 
    failure_threshold=5, 
    recovery_timeout=30.0
)

async def call_mcp_tool(tool_name: str, arguments: dict) -> Dict[str, Any]:
    """
    Unified Client for communicating with the Modular MCP Server.
    Handles JSON-RPC 2.0 protocol, Authentication, and Circuit Breaking.
    """
    async def _execute():
        headers = {
            "X-API-Key": settings.MCP_INTERNAL_API_KEY,
            "Accept": "application/json",
            "Content-Type": "application/json"
        }
        
        # Unique session per tool call to keep MCP server logs clean
        session_id = f"mcp-{tool_name}-{id(arguments)}"
        post_url = f"{settings.MCP_SERVER_URL}/messages?session_id={session_id}"
        
        rpc_payload = {
            "jsonrpc": "2.0",
            "method": "tools/call",
            "params": {
                "name": tool_name,
                "arguments": arguments
            },
            "id": 1
        }

        # Provisioning tools (like xweb) might need's longer timeouts
        timeout_seconds = 60.0 if "xweb" in tool_name else 15.0
        
        async with httpx.AsyncClient(timeout=httpx.Timeout(timeout_seconds)) as client:
            logger.info(f"MCP CALL: {tool_name} -> {post_url}")
            response = await client.post(post_url, json=rpc_payload, headers=headers)
            response.raise_for_status()
            
            data = response.json()
            if "error" in data:
                logger.error(f"MCP RPC Error: {data['error']}")
                return {"error": data["error"].get("message", "Unknown RPC Error")}
                
            # MCP standard returns content list
            result_data = data.get("result", {})
            content_list = result_data.get("content", [])
            
            if content_list and content_list[0].get("type") == "text":
                text_res = content_list[0].get("text", "")
                try:
                    # Some MCP tools return stringified JSON, try to parse for the AI
                    if text_res.strip().startswith(("{", "[")):
                        return json.loads(text_res.replace("'", '"'))
                    return {"result": text_res}
                except Exception:
                    return {"result": text_res}
            
            return result_data

    try:
        return await mcp_circuit.call(_execute)
    except Exception as e:
        logger.error(f"MCP Unified Client Failure ({mcp_circuit.state.value}): {str(e)}")
        return {
            "error": "Công cụ hiện không khả dụng do lỗi kết nối hoặc hệ thống đang bảo trì.",
            "details": str(e)
        }
