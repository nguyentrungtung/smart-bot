import socketio
import asyncio
import base64
import os
import sys
from pathlib import Path

# Add core_backend to path for imports
sys.path.append(str(Path(__file__).parent.parent))
from scripts.generate_test_token import generate_token

SERVER_URL = "http://localhost:8000"

# Using a standard 1-second silent webm base64 for testing if no file exists
# This is a valid 1s silent opus webm
SILENT_WEBM = (
    "GkXfo59ChoEBQveBAULygQRC84EIQoKEd2VibUKHgQRChYECGFOAZwEAAAAAABqFAWh0dHBzOi8vd3d3Lmdvb2dsZS5jb20vY2hyb21lL2Jyb3dzZXIv"
    "YWJvdXQvAAABAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAABfX19fX19fX19fX18="
)

async def test_voice_flow():
    sio = socketio.AsyncClient()
    response_received = asyncio.Event()
    tokens = []
    
    token = generate_token()
    if not token:
        print("Failed to generate token.")
        return

    @sio.event
    async def connect():
        print(f"[CLIENT] Connected to server at {SERVER_URL}")
        print(f"[CLIENT] Sending voice request...")
        await sio.emit("message", {
            "content": "Đây là tin nhắn bằng giọng nói. Bạn có nghe rõ không?",
            "session_id": "test-voice-session",
            "image": None,
            "audio": SILENT_WEBM
        })

    @sio.on("message_stream")
    async def on_message_stream(data):
        token = data.get("chunk", "")
        tokens.append(token)
        print(token, end="", flush=True)

    @sio.on("message_complete")
    async def on_message_complete(data):
        print("\n[CLIENT] Voice session complete.")
        response_received.set()

    @sio.on("error")
    async def on_error(data):
        print(f"\n[CLIENT] Error: {data}")
        response_received.set()

    try:
        await sio.connect(SERVER_URL, auth={'token': token})
        await asyncio.wait_for(response_received.wait(), timeout=60.0)
        print("\nSUCCESS: Voice flow (authenticated) verified.")
    except Exception as e:
        print(f"\n[CLIENT] Error: {str(e)}")
    finally:
        await sio.disconnect()

if __name__ == "__main__":
    asyncio.run(test_voice_flow())
