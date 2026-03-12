import httpx
import logging
import asyncio
import json
from typing import Dict, Any, Optional
from app.config.settings import settings
from app.utils.resilience import get_circuit_breaker

logger = logging.getLogger(__name__)


# Initialize Circuit Breaker for basic tools
basic_circuit = get_circuit_breaker(
    name="basic_tools", 
    failure_threshold=3, 
    recovery_timeout=30.0
)

async def _call_mcp_tool(tool_name: str, arguments: dict) -> Dict[str, Any]:
    """
    Client talking to the Unified/Modular MCP Server.
    Wrapped in a Circuit Breaker for resilience.
    """
    async def _execute():
        headers = {
            "X-API-Key": settings.MCP_INTERNAL_API_KEY,
            "Accept": "application/json",
            "Content-Type": "application/json"
        }
        
        session_id = f"session-{tool_name}"
        # Use settings instead of hardcoded localhost
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

        async with httpx.AsyncClient(timeout=httpx.Timeout(5.0)) as client:
            logger.info(f"MCP DEBUG: Requesting {post_url} with key={settings.MCP_INTERNAL_API_KEY[:5]}***")
            logger.info(f"Calling MCP Tool: {tool_name} at {post_url}")
            response = await client.post(post_url, json=rpc_payload, headers=headers)
            logger.info(f"MCP Response Status: {response.status_code}")
            response.raise_for_status()
            data = response.json()
            logger.info(f"MCP Response Data: {data}")
            
            content_list = data.get("result", {}).get("content", [])
            if content_list and content_list[0].get("type") == "text":
                text_res = content_list[0].get("text", "{}")
                try:
                    if text_res.startswith("{"):
                        # Handle potential single-quote JSON from str(dict)
                        parsed = json.loads(text_res.replace("'", '"'))
                        logger.info(f"Parsed Tool Result: {parsed}")
                        return parsed
                    return {"result": text_res}
                except Exception as parse_err:
                    logger.warning(f"Failed to parse tool text result: {parse_err}. Text: {text_res}")
                    return {"result": text_res}
            return data.get("result", {})

    try:
        # Execute via Circuit Breaker
        return await basic_circuit.call(_execute)
    except Exception as e:
        # FAIL LOUDLY: Let the AI know the tool failed so it can inform the user.
        logger.error(f"Basic Tools MCP Failure (Circuit={basic_circuit.state.value}): {e}")
        return {
            "error": "Dịch vụ công cụ (Basic Tools) hiện không khả dụng hoặc lỗi kết nối.",
            "details": str(e),
            "circuit_state": basic_circuit.state.value
        }

async def get_weather(location: str) -> Dict[str, Any]:
    """Lấy thông tin thời tiết via MCP (Dữ liệu thực)."""
    return await _call_mcp_tool("get_weather", {"location": location})

async def get_current_time(timezone: str = "Asia/Ho_Chi_Minh") -> Dict[str, Any]:
    """Lấy thời gian hiện tại via MCP."""
    return await _call_mcp_tool("get_current_time", {"timezone": timezone})

