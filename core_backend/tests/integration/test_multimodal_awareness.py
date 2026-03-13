import asyncio
import logging
import sys
import os
import base64

# Add the project root to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from langchain_core.messages import HumanMessage
from app.workflows.graph import get_agent_graph
from app.multimodal.processor import MultimodalProcessor

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("test_multimodal")

async def run_scenario_vision():
    """
    Kịch bản 2: Hội thoại hình ảnh (5-10 tin nhắn) để kiểm tra:
    1. Xử lý Image content blocks gửi sang LLM.
    2. Khả năng hiểu ngữ cảnh từ hình ảnh trước đó.
    3. Trình tự phối hợp Text + Image.
    """
    print("\n" + "="*50)
    print("🚀 BẮT ĐẦU TEST HỘI THOẠI HÌNH ẢNH (VISION)")
    print("="*50 + "\n")

    thread_id = f"test-vision-{os.urandom(4).hex()}"
    config = {"configurable": {"thread_id": thread_id}}
    graph = get_agent_graph()
    processor = MultimodalProcessor()

    # Mock Base64 Image (Small red dot)
    mock_image_b64 = "iVBORw0KGgoAAAANSUhEUgAAAAUAAAAFCAYAAACNbyblAAAAHElEQVQI12P4//8/w38GIAXDIBKE0DHxgljNBAAO9TXL0Y4OHwAAAABJRU5ErkJggg=="

    # Kịch bản các bước
    steps = [
        {
            "user": "Chào bạn, tôi gửi cho bạn xem cái bảng hiệu shop của tôi nhé.",
            "image": None
        },
        {
            "user": "Đây là logo của shop, bạn thấy sao?",
            "image": mock_image_b64
        },
        {
            "user": "Trong cái ảnh tôi vừa gửi, có màu sắc nào nổi bật không?",
            "image": None # Test vision memory
        },
        {
            "user": "Tôi muốn dùng màu đỏ đó làm theme cho Xweb, bạn giúp tôi được không?",
            "image": None
        },
        {
            "user": "Gửi thêm cho bạn ảnh mặt bằng shop này.",
            "image": mock_image_b64
        },
        {
            "user": "Tóm tắt lại các yêu cầu về hình ảnh của tôi nãy giờ.",
            "image": None
        }
    ]

    for i, step in enumerate(steps):
        user_text = step["user"]
        img_b64 = step["image"]
        
        print(f"\n👉 [User {i+1}/{len(steps)}]: {user_text} {'(Kèm ảnh)' if img_b64 else ''}")

        # Chuẩn bị message content
        if img_b64:
            # Dùng processor để tạo structure chuẩn LangChain/LiteLLM
            content = processor.process_image_message(user_text, [img_b64])
            msg = HumanMessage(content=content)
        else:
            msg = HumanMessage(content=user_text)

        input_state = {"messages": [msg]}
        
        try:
            output = await graph.ainvoke(input_state, config=config)
            final_msg = output["messages"][-1].content
            print(f"🤖 [AI]: {final_msg}")
            await asyncio.sleep(0.5)
        except Exception as e:
            logger.error(f"Lỗi Vision tại bước {i+1}: {str(e)}")
            break

    print("\n" + "="*50)
    print("✅ HOÀN THÀNH TEST HÌNH ẢNH")
    print("="*50 + "\n")

if __name__ == "__main__":
    asyncio.run(run_scenario_vision())
