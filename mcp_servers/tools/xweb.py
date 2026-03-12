import logging
import asyncio
import uuid
from pydantic import BaseModel, Field
import mcp.types as types

logger = logging.getLogger("mcp_server.xweb")

class CreateXwebParams(BaseModel):
    business_type: str = Field(description="Loại hình kinh doanh (e.g., 'ecommerce', 'blog', 'portfolio')")
    theme_color: str = Field(description="Màu sắc chủ đạo (hex hoặc tên màu)")
    admin_email: str = Field(description="Email quản trị")

async def create_xweb_instance(arguments: dict) -> list[types.TextContent]:
    """Giả lập việc khởi tạo một website Xweb mới."""
    if not arguments:
        raise ValueError("Thiếu tham số cho create_xweb_instance")
    
    params = CreateXwebParams(**arguments)
    logger.info(f"--- [TOOL CALL] create_xweb_instance start for {params.admin_email} ---")
    
    await asyncio.sleep(3) # Simulate loading/provisioning
    mock_domain = f"{params.business_type}-{uuid.uuid4().hex[:6]}.company-xweb.com"
    
    result_text = (
        f"Khởi tạo website thành công!\n"
        f"- Tên miền: https://{mock_domain}\n"
        f"- Loại: {params.business_type}\n"
        f"- Quản trị: {params.admin_email}\n"
        f"Hệ thống đang gửi thông tin đăng nhập vào email của bạn."
    )
    
    logger.info(f"--- [TOOL SUCCESS] create_xweb_instance completed for {params.admin_email} ---")
    return [types.TextContent(type="text", text=result_text)]
