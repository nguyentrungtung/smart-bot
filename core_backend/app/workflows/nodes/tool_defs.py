"""
Tool Definitions & Shared Constants for the Generate Node.
Extracted from generate.py for cleanliness.
"""

# Keywords that allow bypassing the hallucination guard
BYPASS_KEYWORDS = [
    "thời tiết", "thoi tiet", "mấy giờ", "may gio", "ngày mấy", "ngay may",
    "ngày", "tháng", "năm", "giờ", "hôm nay", "bây giờ", "la sao", "là sao",
    "tạo xweb", "xweb",
    "xin chào", "xin chao", "hello", "hi", "chào",
]

# Tool Definitions for LiteLLM (OpenAI-compatible format)
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "Lấy thông tin thời tiết hiện tại của một địa điểm cụ thể.",
            "parameters": {
                "type": "object",
                "properties": {
                    "location": {"type": "string", "description": "Tỉnh/Thành phố (ví dụ: Hà Nội, Hồ Chí Minh)"}
                },
                "required": ["location"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_current_time",
            "description": "Lấy ngày giờ hiện tại và thứ trong tuần theo múi giờ.",
            "parameters": {
                "type": "object",
                "properties": {
                    "timezone": {"type": "string", "description": "Múi giờ (mặc định: Asia/Ho_Chi_Minh)"}
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "create_xweb_instance",
            "description": "Khởi tạo một instance Xweb mới cho khách hàng. Cần sự phê duyệt của quản lý.",
            "parameters": {
                "type": "object",
                "properties": {
                    "business_type": {"type": "string", "description": "Loại hình kinh doanh (ví dụ: Shop quần áo, Nhà hàng)"},
                    "theme_color": {"type": "string", "description": "Màu chủ đạo (hex hoặc tên màu)"},
                    "admin_email": {"type": "string", "description": "Email quản trị viên"}
                },
                "required": ["business_type", "theme_color", "admin_email"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "update_user_profile",
            "description": "Cập nhật thông tin cá nhân hoặc sở thích dài hạn của người dùng vào cơ sở dữ liệu.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Tên của người dùng"},
                    "preferences": {"type": "object", "description": "Sở thích mới (ví dụ: {'tone': 'technical'})"},
                    "new_facts": {"type": "array", "items": {"type": "string"}, "description": "Danh sách các sự thật mới về người dùng"}
                }
            }
        }
    }
]
