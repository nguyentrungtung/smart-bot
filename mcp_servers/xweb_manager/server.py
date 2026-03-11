import asyncio
import os
import uuid
import logging
from typing import Optional
from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from mcp.server import Server
from mcp.server.sse import SseServerTransport
import mcp.types as types

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("xweb_mcp")

# --- Security ---
INTERNAL_API_KEY = os.environ.get("MCP_INTERNAL_API_KEY", "dev-secure-mcp-key-123")

# --- MCP Server Initializing ---
mcp = Server("xweb_manager")

# --- MCP Tool Schemas ---
class CreateXwebParams(BaseModel):
    business_type: str = Field(description="The type of business (e.g., 'ecommerce', 'blog', 'portfolio')")
    theme_color: str = Field(description="Primary hex color or descriptive color string")
    admin_email: str = Field(description="Email address for the initial admin account")

@mcp.list_tools()
async def handle_list_tools() -> list[types.Tool]:
    """List available tools."""
    return [
        types.Tool(
            name="create_xweb_instance",
            description="Simulates provisioning a new Xweb website instance.",
            inputSchema=CreateXwebParams.model_json_schema()
        )
    ]

@mcp.call_tool()
async def handle_call_tool(name: str, arguments: dict | None) -> list[types.TextContent]:
    """Handle tool calls."""
    if name == "create_xweb_instance":
        if not arguments:
            raise ValueError("Missing arguments for create_xweb_instance")
        
        params = CreateXwebParams(**arguments)
        logger.info(f"Creating Xweb instance for {params.admin_email}")
        
        await asyncio.sleep(3) # Simulate loading
        mock_domain = f"{params.business_type}-{uuid.uuid4().hex[:6]}.company-xweb.com"
        
        result_json = {
            "status": "success",
            "url": f"https://{mock_domain}",
            "admin_email": params.admin_email
        }
        
        return [types.TextContent(type="text", text=str(result_json))]
        
    raise ValueError(f"Unknown tool: {name}")

# --- SSE Transport Logic ---
sse_transport = SseServerTransport("/messages")

@asynccontextmanager
async def lifespan(app: FastAPI):
    # This runs the MCP server in the background
    async def run_mcp():
        async with mcp.run_all_transports() as loop:
            await loop
    
    # We don't block here, but we could use background task if needed
    # In standard SSE, we handle connect/message differently
    yield

app = FastAPI(title="Xweb Manager MCP Server")

# --- Routes for SSE ---
@app.get("/sse")
async def sse_connect(request: Request):
    """
    Initiates the SSE connection.
    Security: Checked via Middleware below.
    """
    async with sse_transport.connect_sse(request.scope, request.receive, request._send) as (read_stream, write_stream):
        await mcp.run(
            read_stream,
            write_stream,
            mcp.create_initialization_options()
        )

@app.post("/messages")
async def handle_messages(request: Request):
    """
    Handles incoming messages from the client.
    """
    await sse_transport.handle_post_message(request.scope, request.receive, request._send)

# --- Security Middleware ---
@app.middleware("http")
async def enforce_api_key_middleware(request: Request, call_next):
    # Protect both connection and message endpoints
    if request.url.path in ["/sse", "/messages"]:
        api_key_header = request.headers.get("X-API-Key")
        if not api_key_header or api_key_header != INTERNAL_API_KEY:
            logger.warning("Unauthorized access to Xweb MCP Server")
            return JSONResponse(status_code=403, content={"detail": "Forbidden"})
    return await call_next(request)

@app.get("/health")
async def health_check():
    return {"status": "ok", "service": "xweb_manager"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8002)
