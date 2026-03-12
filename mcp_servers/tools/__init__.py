from typing import Dict, Any, Callable, Awaitable
from mcp.server import Server
import mcp.types as types

from .weather import get_weather, WeatherParams
from .time import get_current_time, TimeParams
from .xweb import create_xweb_instance, CreateXwebParams

async def handle_call_tool(name: str, arguments: dict | None) -> list[types.TextContent]:
    """Xử lý gọi tool thực tế."""
    arguments = arguments or {}
    match name:
        case "get_weather":
            return await get_weather(arguments)
        case "get_current_time":
            return await get_current_time(arguments)
        case "create_xweb_instance":
            return await create_xweb_instance(arguments)
        case _:
            raise ValueError(f"Không tìm thấy tool: {name}")

def register_tools(mcp_server: Server):
    """Đăng ký tất cả các tools vào MCP Server."""
    
    @mcp_server.list_tools()
    async def handle_list_tools() -> list[types.Tool]:
        return [
            types.Tool(
                name="get_weather",
                description="Lấy thông tin thời tiết hiện tại của một địa điểm cụ thể.",
                inputSchema=WeatherParams.model_json_schema()
            ),
            types.Tool(
                name="get_current_time",
                description="Lấy ngày giờ hiện tại của hệ thống.",
                inputSchema=TimeParams.model_json_schema()
            ),
            types.Tool(
                name="create_xweb_instance",
                description="Khởi tạo một website xweb mới cho khách hàng.",
                inputSchema=CreateXwebParams.model_json_schema()
            )
        ]

    # Register the call_tool handler
    mcp_server.call_tool()(handle_call_tool)
