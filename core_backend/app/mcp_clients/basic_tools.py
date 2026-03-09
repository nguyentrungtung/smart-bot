from typing import Dict, Any

async def get_weather(location: str) -> Dict[str, Any]:
    """
    Client talking to the Basic Tools MCP Server over SSE.
    """
    pass

async def get_current_time(timezone: str) -> Dict[str, Any]:
    """
    Client talking to the Basic Tools MCP Server for timezone calculations.
    """
    pass
