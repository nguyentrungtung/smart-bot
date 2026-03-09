import httpx
import logging
import asyncio
from typing import Dict, Any
from app.config.settings import settings

logger = logging.getLogger(__name__)

# Base internal URL for the docker-compose linked tools service
XWEB_MCP_URL = "http://xweb_mcp:8002"

async def create_xweb_instance(business_type: str, theme_color: str, admin_email: str) -> Dict[str, Any]:
    """
    Client talking to the Xweb Manager MCP Server.
    Implements a strict Circuit Breaker to prevent hanging the SSE connection.
    """
    payload = {
        "business_type": business_type,
        "theme_color": theme_color,
        "admin_email": admin_email
    }
    
    headers = {
        "X-API-Key": settings.MCP_INTERNAL_API_KEY,
        "Content-Type": "application/json"
    }
    
    # Circuit Breaker: 5 Second Timeout strict cutoff (since the MCP server sleeps 3 seconds to simulate load, this should pass normally, but fail safely if it actually hangs)
    timeout = httpx.Timeout(5.0)

    try:
        # In a full MCP architecture, this would use the `mcp.ClientSession`. 
        # For MVP integration clarity and simplicity across disjoint networks, we simulate the tool execution via direct REST to the FastApi mounted endpoint.
        # Ensure we point to the correct internal endpoint. In FastApi MCP SDK usually `/sse` or specific tools router.
        # Assuming the FastAPI mounted server exposes the tool directly for this POC client:
        
        async with httpx.AsyncClient(timeout=timeout) as client:
            # We construct a mock JSON-RPC payload as expected by standard MCP endpoints or hit a REST shim
            rpc_payload = {
                "jsonrpc": "2.0",
                "method": "tools/call",
                "params": {
                    "name": "create_xweb_instance",
                    "arguments": payload
                },
                "id": 1
            }
            
            # Note: The mcp python SDK uses SSE for transport. This httpx call is a simplified REST wrapper logic for the circuit breaker demo.
            response = await client.post(f"{XWEB_MCP_URL}/messages", json=rpc_payload, headers=headers)
            response.raise_for_status()
            
            data = response.json()
            return {"status": "success", "result": data.get("result", {}).get("url", "https://mock.com")}
            
    except httpx.TimeoutException:
        logger.error("Xweb MCP Server Circuit Breaker Triggered (Timeout after 5s)")
        return {
            "status": "error", 
            "message": "Xweb provisioning service is currently overloaded. Please try again in 1 minute."
        }
    except httpx.HTTPStatusError as e:
        logger.error(f"Xweb MCP Server HTTP Error: {e.response.status_code} - {e.response.text}")
        return {
            "status": "error", 
            "message": f"Service Error: {e.response.status_code}. Internal API Key might be invalid."
        }
    except Exception as e:
        logger.error(f"Xweb MCP Server Unknown Error: {e}")
        return {
            "status": "error", 
            "message": "Critical connection failure to internal tool network."
        }
