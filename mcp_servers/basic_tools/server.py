import asyncio
import os
import logging
import datetime
from typing import Dict, Any
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from mcp.server import Server
from mcp.server.sse import SseServerTransport
import mcp.types as types

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("basic_tools_mcp")

# --- Security ---
INTERNAL_API_KEY = os.environ.get("MCP_INTERNAL_API_KEY", "dev-secure-mcp-key-123")

# --- MCP Server Initializing ---
mcp = Server("basic_tools")

# --- Tool Schemas ---
class WeatherParams(BaseModel):
    location: str = Field(description="The city or region to get weather for (e.g., 'Hanoi', 'Ho Chi Minh')")

class TimeParams(BaseModel):
    timezone: str = Field(default="Asia/Ho_Chi_Minh", description="The timezone to get time for")

@mcp.list_tools()
async def handle_list_tools() -> list[types.Tool]:
    """List available tools."""
    return [
        types.Tool(
            name="get_weather",
            description="Lấy thông tin thời tiết hiện tại của một địa điểm cụ thể.",
            inputSchema=WeatherParams.model_json_schema()
        ),
        types.Tool(
            name="get_current_time",
            description="Lấy ngày giờ hiện tại và thứ trong tuần theo múi giờ.",
            inputSchema=TimeParams.model_json_schema()
        )
    ]

import httpx

@mcp.call_tool()
async def handle_call_tool(name: str, arguments: dict | None) -> list[types.TextContent]:
    """Handle tool calls."""
    match name:
        case "get_weather":
            location = arguments.get("location", "Hanoi")
            logger.info(f"Fetching real weather for {location}")
            
            # Simple Geocoding mapping for common cities in Vietnam
            # In a production app, use a real geocoding API or library.
            geocoding = {
                "hanoi": (21.0285, 105.8542),
                "ha noi": (21.0285, 105.8542),
                "hồ chí minh": (10.7626, 106.6602),
                "ho chi minh": (10.7626, 106.6602),
                "hcm": (10.7626, 106.6602),
                "saigon": (10.7626, 106.6602),
                "da nang": (16.0544, 108.2022),
                "da nang": (16.0544, 108.2022),
                "can tho": (10.0452, 105.7469),
                "hai phong": (20.8449, 106.6881)
            }
            
            city_key = location.lower().strip()
            lat, lon = geocoding.get(city_key, (21.0285, 105.8542)) # Default to Hanoi
            
            try:
                weather_url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current_weather=true"
                async with httpx.AsyncClient(timeout=10.0) as client:
                    resp = await client.get(weather_url)
                    resp.raise_for_status()
                    data = resp.json()
                    
                    current = data.get("current_weather", {})
                    temp = current.get("temperature")
                    windspeed = current.get("windspeed")
                    weathercode = current.get("weathercode")
                    
                    # Basic weather code mapping
                    condition = "Clear/Sunny"
                    if weathercode >= 1 and weathercode <= 3: condition = "Partly Cloudy"
                    elif weathercode >= 45: condition = "Cloudy/Foggy"
                    elif weathercode >= 51: condition = "Rainy"
                    
                    result = {
                        "location": location,
                        "temperature": f"{temp}°C",
                        "condition": condition,
                        "windspeed": f"{windspeed} km/h",
                        "latitude": lat,
                        "longitude": lon,
                        "source": "Open-Meteo"
                    }
                    return [types.TextContent(type="text", text=str(result))]
            except Exception as e:
                logger.error(f"Error fetching weather from API: {e}")
                return [types.TextContent(type="text", text=f"Error: Could not fetch weather for {location}. Details: {str(e)}")]
            
        case "get_current_time":
            tz = arguments.get("timezone", "Asia/Ho_Chi_Minh")
            logger.info(f"Fetching current time for {tz}")
            now = datetime.datetime.now()
            result = {
                "timezone": tz,
                "current_time": now.strftime("%Y-%m-%d %H:%M:%S"),
                "day_of_week": now.strftime("%A")
            }
            return [types.TextContent(type="text", text=str(result))]
            
        case _:
            raise ValueError(f"Unknown tool: {name}")

# --- SSE Transport Logic ---
sse_transport = SseServerTransport("/messages")

app = FastAPI(title="Basic Tools MCP Server")

@app.get("/sse")
async def sse_connect(request: Request):
    """Initiates the SSE connection."""
    async with sse_transport.connect_sse(request.scope, request.receive, request._send) as (read_stream, write_stream):
        await mcp.run(
            read_stream,
            write_stream,
            mcp.create_initialization_options()
        )

@app.post("/messages")
async def handle_messages(request: Request):
    """Handles incoming messages. Supports both SSE session-based and direct tool calls."""
    try:
        body = await request.json()
    except:
        body = {}

    # Direct Call logic for stateless clients (e.g. core_backend)
    if body.get("method") == "tools/call":
        params = body.get("params", {})
        name = params.get("name")
        args = params.get("arguments")
        logger.info(f"Direct tool call received: {name}")
        try:
            result_content = await handle_call_tool(name, args)
            return {
                "jsonrpc": "2.0",
                "id": body.get("id"),
                "result": {
                    "content": [
                        {"type": "text", "text": c.text if hasattr(c, "text") else str(c)} 
                        for c in result_content
                    ]
                }
            }
        except Exception as e:
            logger.error(f"Error in direct tool call: {e}")
            return JSONResponse(
                status_code=500,
                content={"jsonrpc": "2.0", "id": body.get("id"), "error": {"code": -32603, "message": str(e)}}
            )

    # Standard SSE Transport (requires session_id)
    session_id = request.query_params.get("session_id")
    if session_id:
        return await sse_transport.handle_post_message(request.scope, request.receive, request._send)

    return JSONResponse(status_code=400, content={"detail": "session_id required for non-tool-call messages"})

# --- Security Middleware ---
@app.middleware("http")
async def enforce_api_key_middleware(request: Request, call_next):
    if request.url.path in ["/sse", "/messages"]:
        api_key_header = request.headers.get("X-API-Key")
        if not api_key_header or api_key_header != INTERNAL_API_KEY:
            logger.warning("Unauthorized access to Basic Tools MCP Server")
            return JSONResponse(status_code=403, content={"detail": "Forbidden"})
    return await call_next(request)

@app.get("/health")
async def health_check():
    return {"status": "ok", "service": "basic_tools"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
