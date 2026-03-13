import asyncio
import logging
import sys
import os

# Add the project root to sys.path to allow importing 'app'
# Add the project root (core_backend) to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from langchain_core.messages import HumanMessage
from app.workflows.graph import get_agent_graph
from app.config.settings import settings

# Configure logging to show the MEMORY DEBUG and TOKEN USAGE logs
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("test_long_conv")

async def run_scenario_long_text():
    """
    Kịch bản 1: Hội thoại dài (10-20 tin nhắn) để kiểm tra:
    1. Checkpointer (MemorySaver) hoạt động đúng qua thread_id.
    2. Summarizer kích hoạt khi đạt threshold.
    3. AI duy trì sự nhất quán về thông tin (Tên, sở thích).
    """
    print("\n" + "="*50)
    print("🚀 BẮT ĐẦU TEST HỘI THOẠI DÀI (10-20 TIN NHẮN)")
    print("="*50 + "\n")

    # Giả lập thread_id duy nhất cho session này
    thread_id = f"test-long-text-{os.urandom(4).hex()}"
    config = {"configurable": {"thread_id": thread_id}}
    
    graph = get_agent_graph()

    # Danh sách các câu hỏi giả lập một cuộc hội thoại thực tế
    prompts = [
        "Chào bạn, tôi tên là Tùng, tôi đang tìm hiểu về giải pháp Xweb.",
        "Xweb có tính năng gì đặc biệt không?",
        "Tôi muốn làm một website cho shop quần áo, màu chủ đạo là xanh dương.",
        "Bạn có biết thời tiết ở Hà Nội hôm nay thế nào không? Tôi định đi khảo sát cửa hàng.",
        "Quay lại chuyện Xweb, nó có hỗ trợ thanh toán online không?",
        "À mà tôi vừa bảo tên tôi là gì ấy nhỉ?", # Test Short-term memory
        "Tôi thích phong cách thiết kế tối giản, bạn ghi chú lại nhé.", # Test Profile updating
        "Hiện tại là mấy giờ rồi?", # Test Local Tool
        "Giải thích cho tôi về quy trình triển khai ISO 9001.", # Test RAG
        "Tại sao doanh nghiệp cần ISO 9001?",
        "Quay lại chuyện shop quần áo của tôi, bạn nhớ màu chủ đạo tôi thích là gì không?", # Test Long-term memory/Summary
        "Tóm tắt lại nãy giờ chúng ta đã thảo luận những gì?",
        "Tôi muốn tạo một instance Xweb ngay bây giờ được không?",
        "Email của tôi là tung@example.com, hãy dùng nó cho Xweb.",
        "Cảm ơn bạn, bạn phục vụ rất tốt!",
    ]

    for i, p in enumerate(prompts):
        print(f"\n👉 [User {i+1}/{len(prompts)}]: {p}")
        
        # Gọi graph xử lý
        input_state = {"messages": [HumanMessage(content=p)]}
        
        # Dùng astream để thấy token stream (optional) hoặc ainvoke cho nhanh
        # Ở đây dùng ainvoke để kiểm tra trạng thái cuối cùng của mỗi turn
        try:
            output = await graph.ainvoke(input_state, config=config)
            final_msg = output["messages"][-1].content
            
            # Highlight AI Response
            print(f"🤖 [AI]: {final_msg[:100]}..." if len(final_msg) > 100 else f"🤖 [AI]: {final_msg}")
            
            # Small delay to keep logs readable
            await asyncio.sleep(0.5)
            
        except Exception as e:
            logger.error(f"Lỗi tại tin nhắn thứ {i+1}: {str(e)}")
            break

    print("\n" + "="*50)
    print("✅ HOÀN THÀNH TEST HỘI THOẠI DÀI")
    print("Vui lòng kiểm tra console logs để xem [MEMORY DEBUG] và [TOKEN USAGE DEBUG]")
    print("="*50 + "\n")

if __name__ == "__main__":
    # Đảm bảo set biến môi trường nếu chạy local (ví dụ DB URL)
    # settings load từ .env mặc định
    asyncio.run(run_scenario_long_text())
