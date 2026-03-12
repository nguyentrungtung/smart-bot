import httpx
import logging
from typing import Dict, Any
from app.config.settings import settings
from app.utils.resilience import get_circuit_breaker

logger = logging.getLogger(__name__)

# Use the unified MCP URL from settings
XWEB_MCP_URL = settings.MCP_SERVER_URL

# Initialize Circuit Breaker for Xweb
xweb_circuit = get_circuit_breaker(
    name="xweb_tools", 
    failure_threshold=2, # Stricter for high-risk tools
    recovery_timeout=60.0 # Longer recovery for infrastructure provisioning
)

async def create_xweb_instance(business_type: str, theme_color: str, admin_email: str) -> Dict[str, Any]:
    """
    Client talking to the Unified/Modular MCP Server.
    Wrapped in a Circuit Breaker to prevent long hangs during provisioning spikes.
    """
    async def _execute():
        payload = {
            "business_type": business_type,
            "theme_color": theme_color,
            "admin_email": admin_email
        }
        
        headers = {
            "X-API-Key": settings.MCP_INTERNAL_API_KEY,
            "Content-Type": "application/json"
        }
        
        rpc_payload = {
            "jsonrpc": "2.0",
            "method": "tools/call",
            "params": {
                "name": "create_xweb_instance",
                "arguments": payload
            },
            "id": 1
        }
        
        async with httpx.AsyncClient(timeout=httpx.Timeout(10.0)) as client:
            response = await client.post(f"{XWEB_MCP_URL}/messages", json=rpc_payload, headers=headers)
            response.raise_for_status()
            data = response.json()
            return {"status": "success", "result": data.get("result", {}).get("url", "https://mock-xweb.com")}

    try:
        return await xweb_circuit.call(_execute)
    except httpx.TimeoutException:
        logger.error("Xweb MCP Timeout (Circuit Breaker will note this)")
        return {
            "status": "error", 
            "message": "Xweb service timed out. The request might still be processing, but the connection was closed for resilience."
        }
    except Exception as e:
        logger.error(f"Xweb Resource Failure (Circuit={xweb_circuit.state.value}): {e}")
        return {
            "status": "error", 
            "message": f"Xweb service is currently unavailable (Circuit={xweb_circuit.state.value}). Please try again later."
        }
