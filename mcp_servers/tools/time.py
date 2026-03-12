import logging
import datetime
from pydantic import BaseModel, Field
import mcp.types as types

logger = logging.getLogger("mcp_server.time")

class TimeParams(BaseModel):
    timezone: str = Field(default="Asia/Ho_Chi_Minh", description="Múi giờ (ví dụ: 'Asia/Ho_Chi_Minh')")

async def get_current_time(arguments: dict) -> list[types.TextContent]:
    """Lấy ngày giờ hiện tại."""
    tz = arguments.get("timezone", "Asia/Ho_Chi_Minh")
    logger.info(f"--- [TOOL CALL] get_current_time start: tz={tz} ---")
    
    # Ở phiên bản MVP này chúng ta lấy giờ hệ thống server
    now = datetime.datetime.now()
    res_text = f"Thời gian hiện tại của hệ thống: {now.strftime('%H:%M:%S, %d/%m/%Y')} (Thứ {now.isoweekday() + 1 if now.isoweekday() < 7 else 'Chủ Nhật'})"
    
    logger.info(f"--- [TOOL SUCCESS] get_current_time: {res_text} ---")
    return [types.TextContent(type="text", text=res_text)]
