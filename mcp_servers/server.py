import os
import logging
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from mcp.server import Server
from mcp.server.sse import SseServerTransport
from tools import register_tools
from dotenv import load_dotenv

load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("mcp_server")

# --- Security ---
INTERNAL_API_KEY = os.environ.get("MCP_INTERNAL_API_KEY", "dev-secure-mcp-key-123")

# --- MCP Server Initializing ---
mcp = Server("unified_mcp_server")
register_tools(mcp)

# --- SSE Transport Logic ---
sse_transport = SseServerTransport("/messages")

app = FastAPI(title="Unified Smart-Bot MCP Server")

@app.get("/sse")
async def sse_connect(request: Request):
    """Bắt đầu kết nối SSE."""
    async with sse_transport.connect_sse(request.scope, request.receive, request._send) as (read_stream, write_stream):
        await mcp.run(
            read_stream,
            write_stream,
            mcp.create_initialization_options()
        )

@app.post("/messages")
async def handle_messages(request: Request):
    """Xử lý tin nhắn đến. Hỗ trợ cả SSE (session) và gọi tool trực tiếp (stateless)."""
    try:
        body = await request.json()
    except:
        body = {}

    # Logic gọi tool trực tiếp cho các client stateless (như core_backend)
    if body.get("method") == "tools/call":
        params = body.get("params", {})
        name = params.get("name")
        args = params.get("arguments")
        logger.info(f"Direct tool call received: {name}")
        try:
            from tools import handle_call_tool 
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

    # SSE chuẩn (cần session_id)
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
            logger.warning("Unauthorized access blocked")
            return JSONResponse(status_code=403, content={"detail": "Forbidden"})
    return await call_next(request)

@app.get("/health")
async def health_check():
    return {"status": "ok", "service": "mcp_server"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
