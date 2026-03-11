import socketio
import asyncio
import sys
from pathlib import Path

# Add core_backend to path for imports
sys.path.append(str(Path(__file__).parent.parent))
from scripts.generate_test_token import generate_token

SERVER_URL = "http://localhost:8000"

async def test_bypass_logic():
    sio = socketio.AsyncClient()
    token = generate_token()
    
    if not token:
        print("Failed to generate token.")
        return

    # Phase 1: Test Fallback Trigger (Scenario B)
    # Query: Something unrelated to RAG (Smart-Watch) and not a tool keyword
    fallback_received = asyncio.Event()
    last_response = ""

    @sio.on("message_stream")
    async def on_message_stream_fallback(data):
        nonlocal last_response
        last_response += data.get("chunk", "")

    @sio.on("message_complete")
    async def on_message_complete_fallback(data):
        print(f"\n[PHASE 1] Recieved Response: {last_response}")
        if "tôi chưa rõ tài liệu này" in last_response or "SĐT / Email" in last_response:
            print("SUCCESS: Scenario B Fallback triggered correctly.")
        else:
            print("FAILURE: Scenario B Fallback NOT triggered.")
        fallback_received.set()

    try:
        await sio.connect(SERVER_URL, auth={'token': token})
        print("\n[PHASE 1] Testing Bypass Fallback (Out-of-context query)...")
        await sio.emit("message", {
            "content": "Làm sao để nấu cơm ngon?", # How to cook rice - not in RAG
            "session_id": "test-bypass-session-1"
        })
        await asyncio.wait_for(fallback_received.wait(), timeout=30.0)
    except Exception as e:
        print(f"Error in Phase 1: {e}")
    finally:
        await sio.disconnect()

    # Phase 2: Test Tool Bypass (Should NOT trigger fallback even if RAG is empty)
    sio = socketio.AsyncClient()
    tool_triggered = asyncio.Event()
    last_response = ""
    
    @sio.on("message_stream")
    async def on_message_stream_tool(data):
        nonlocal last_response
        last_response += data.get("chunk", "")

    @sio.on("message_complete")
    async def on_message_complete_tool(data):
        print(f"\n[PHASE 2] Recieved Response: {last_response}")
        # If it's a tool response (time/weather), it won't be the fallback message
        if "tôi chưa rõ tài liệu này" not in last_response:
            print("SUCCESS: Tool request bypassed Scenario B correctly.")
        else:
            print("FAILURE: Tool request was blocked by Scenario B.")
        tool_triggered.set()

    try:
        await sio.connect(SERVER_URL, auth={'token': token})
        print("\n[PHASE 2] Testing Tool Bypass (Keyword: 'Mấy giờ')...")
        await sio.emit("message", {
            "content": "Bây giờ là mấy giờ?",
            "session_id": "test-bypass-session-2"
        })
        await asyncio.wait_for(tool_triggered.wait(), timeout=30.0)
    except Exception as e:
        print(f"Error in Phase 2: {e}")
    finally:
        await sio.disconnect()

if __name__ == "__main__":
    asyncio.run(test_bypass_logic())
