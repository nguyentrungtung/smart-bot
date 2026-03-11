import httpx
import logging
import asyncio
import json
from typing import Dict, Any, Optional
from app.config.settings import settings
from app.utils.resilience import get_circuit_breaker

logger = logging.getLogger(__name__)

# Base internal URL for the docker-compose linked tools service
BASIC_TOOLS_URL = "http://localhost:8001"

# Initialize Circuit Breaker for basic tools
basic_circuit = get_circuit_breaker(
    name="basic_tools", 
    failure_threshold=3, 
    recovery_timeout=30.0
)

async def _call_mcp_tool(tool_name: str, arguments: dict) -> Dict[str, Any]:
    """
    Client talking to the Basic Tools MCP Server.
    Wrapped in a Circuit Breaker for resilience.
    """
    async def _execute():
        headers = {
            "X-API-Key": settings.MCP_INTERNAL_API_KEY,
            "Accept": "application/json",
            "Content-Type": "application/json"
        }
        
        session_id = f"session-{tool_name}"
        post_url = f"{BASIC_TOOLS_URL}/messages?session_id={session_id}"
        
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
            response = await client.post(post_url, json=rpc_payload, headers=headers)
            response.raise_for_status()
            data = response.json()
            
            content_list = data.get("result", {}).get("content", [])
            if content_list and content_list[0].get("type") == "text":
                text_res = content_list[0].get("text", "{}")
                try:
                    if text_res.startswith("{"):
                        return json.loads(text_res.replace("'", '"'))
                    return {"result": text_res}
                except:
                    return {"result": text_res}
            return data.get("result", {})

    try:
        # Execute via Circuit Breaker
        return await basic_circuit.call(_execute)
    except Exception as e:
        # Graceful degradation: If circuit is OPEN or call failed, return fallback
        logger.error(f"Basic Tools Resource Failure (Circuit={basic_circuit.state.value}): {e}")
        return _get_mock_fallback(tool_name, arguments)

def _get_mock_fallback(tool_name: str, args: dict) -> dict:
    match tool_name:
        case "get_weather":
            return {"location": args.get("location"), "temperature": "25°C", "condition": "Mocked (Handshake failed)"}
        case "get_current_time":
            return {"timezone": args.get("timezone"), "current_time": "2024-03-11 10:00:00", "note": "Mocked"}
        case _:
            return {"error": "Tool failed"}

async def get_weather(location: str) -> Dict[str, Any]:
    """Lấy thông tin thời tiết via MCP."""
    return await _call_mcp_tool("get_weather", {"location": location})

async def get_current_time(timezone: str = "Asia/Ho_Chi_Minh") -> Dict[str, Any]:
    """Lấy thời gian hiện tại via MCP."""
    return await _call_mcp_tool("get_current_time", {"timezone": timezone})

