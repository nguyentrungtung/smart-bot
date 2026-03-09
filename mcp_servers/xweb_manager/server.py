import asyncio
import os
import uuid
import logging
from typing import Optional
from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from mcp.server.fastapi import create_mcp_server
from mcp.server import Server

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("xweb_mcp")

# --- Security ---
# Ensure only the Core Backend can call this MCP server
INTERNAL_API_KEY = os.environ.get("MCP_INTERNAL_API_KEY", "dev-secure-mcp-key-123")

async def verify_internal_key(request: Request):
    """
    Dependency to verify internal API key in headers.
    """
    api_key_header = request.headers.get("X-API-Key")
    if not api_key_header or api_key_header != INTERNAL_API_KEY:
        logger.warning("Unauthorized access attempt to Xweb MCP Server")
        raise HTTPException(status_code=403, detail="Forbidden: Invalid Internal API Key")
    return api_key_header

# --- MCP Tool Schemas ---
class CreateXwebParams(BaseModel):
    business_type: str = Field(description="The type of business (e.g., 'ecommerce', 'blog', 'portfolio')")
    theme_color: str = Field(description="Primary hex color or descriptive color string")
    admin_email: str = Field(description="Email address for the initial admin account")
    
# --- Server Setup ---
app = FastAPI(title="Xweb Manager MCP Server")

# Initialize MCP Server instance
mcp = Server("xweb_manager")

@mcp.tool("create_xweb_instance")
async def create_xweb_instance(params: CreateXwebParams) -> str:
    """
    Simulates the heavy, external process of provisioning a new Xweb website instance.
    Uses asyncio.sleep to simulate network latency and returns a mock domain URL.
    """
    logger.info(f"Received request to create Xweb instance for {params.admin_email} ({params.business_type})")
    
    # Simulate network latency and external system provisioning (fail-safe circuit breaker target)
    await asyncio.sleep(3) 
    
    # Simulate success
    mock_domain = f"{params.business_type}-{uuid.uuid4().hex[:6]}.company-xweb.com"
    
    result = {
        "status": "success",
        "message": "Xweb instance provisioned successfully.",
        "url": f"https://{mock_domain}",
        "admin_email": params.admin_email,
        "theme": params.theme_color
    }
    
    return str(result)

# --- FastAPI Integration ---
mcp_app = create_mcp_server(mcp)

# Mount MCP endpoints with the security dependency
app.mount("/sse", mcp_app, name="mcp_sse")

# Example of how the endpoints would be secured if Fastapi allowed dependency injection directly into mount:
# Currently, create_mcp_server handles its own routing. To strictly secure it via FastAPI, 
# we use a middleware to intercept all requests to /sse.
@app.middleware("http")
async def enforce_api_key_middleware(request: Request, call_next):
    if request.url.path.startswith("/sse"):
        api_key_header = request.headers.get("X-API-Key")
        if not api_key_header or api_key_header != INTERNAL_API_KEY:
            logger.warning("Unauthorized access attempt to Xweb MCP Server")
            from fastapi.responses import JSONResponse
            return JSONResponse(status_code=403, content={"detail": "Forbidden: Invalid Internal API Key"})
    response = await call_next(request)
    return response

@app.get("/health")
async def health_check():
    return {"status": "ok", "service": "xweb_manager"}

if __name__ == "__main__":
    import uvicorn
    # Typically run behind a Docker network, bound to 0.0.0.0
    uvicorn.run(app, host="0.0.0.0", port=8002)
