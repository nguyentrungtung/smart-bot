import asyncio
import psycopg
import json
import logging
from app.workflows.graph import get_agent_graph
from langchain_core.messages import HumanMessage

logging.basicConfig(level=logging.INFO)

async def check_memory():
    # 1. Connect to DB to find the latest session
    conn = await psycopg.AsyncConnection.connect("postgresql://admin:admin@localhost:5432/smartsales")
    async with conn.cursor() as cur:
        await cur.execute("SELECT session_id, content FROM chat_interactions ORDER BY created_at DESC LIMIT 5")
        rows = await cur.fetchall()
        print("\n--- CÁC PHIÊN CHAT GẦN ĐÂY ---")
        for r in rows:
            print(f"Session: {r[0]} | Content Snippet: {str(r[1])[:50]}")
        
        if not rows:
            print("Không tìm thấy phiên chat nào.")
            return

        latest_session_id = rows[0][0]
        print(f"\n--- KIỂM TRA MEMORY CỦA SESSION: {latest_session_id} ---")

    # 2. Use LangGraph to get the actual state from checkpoint
    config = {"configurable": {"thread_id": latest_session_id}}
    graph = get_agent_graph()
    state = await graph.aget_state(config)
    
    messages = state.values.get("messages", [])
    print(f"Tổng số tin nhắn trong checkpoint: {len(messages)}")
    
    found_image = False
    for i, msg in enumerate(messages):
        role = "USER" if isinstance(msg, HumanMessage) else "AI"
        
        # Check if content is a list (multimodal)
        if isinstance(msg.content, list):
            print(f"Msg {i} [{role}]: MULTIMODAL (List of {len(msg.content)} blocks)")
            for b in msg.content:
                if b.get("type") in ["image_url", "input_audio"]:
                    found_image = True
                    # Show a tiny bit of the base64 to prove it's there
                    url = b.get("image_url", {}).get("url", "") or b.get("input_audio", {}).get("data", "")
                    print(f"   -> ĐÃ TÌM THẤY DỮ LIỆU THÔ! ({len(url)} ký tự)")
        else:
            # Check if it was scrubbed (look for our tag)
            if "[MÔ TẢ ĐA PHƯƠNG TIỆN]" in str(msg.content):
                print(f"Msg {i} [{role}]: ✅ ĐÃ ĐƯỢC TỐI ƯU HÓA (Văn bản mô tả)")
            else:
                print(f"Msg {i} [{role}]: Text only ({len(msg.content)} chars)")

    if not found_image:
        print("\n=> KẾT QUẢ: KHÔNG tìm thấy dữ liệu ảnh thô (base64) trong memory. Vision Scrubber đã làm việc tốt!")
    else:
        print("\n=> KẾT QUẢ: VẪN CÒN dữ liệu ảnh thô. Cần kiểm tra lại luồng xử lý.")

    await conn.close()

if __name__ == "__main__":
    asyncio.run(check_memory())
