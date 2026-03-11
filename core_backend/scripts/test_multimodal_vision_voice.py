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
IMAGE_PATH = r"c:\Users\Admin\Desktop\smart-bot\scripts\test_img.png"

async def test_multimodal_flow():
    sio = socketio.AsyncClient()
    response_received = asyncio.Event()
    tokens = []
    
    token = generate_token()
    if not token:
        print("Failed to generate token. Keys missing?")
        return

    # Load image
    with open(IMAGE_PATH, "rb") as f:
        img_b64 = base64.b64encode(f.read()).decode()

    @sio.event
    async def connect():
        print(f"[CLIENT] Connected to server at {SERVER_URL}")
        # Send multimodal message
        print(f"[CLIENT] Sending vision request with image: {IMAGE_PATH}")
        await sio.emit("message", {
            "content": "What is in this image? Please describe the dashboard.",
            "session_id": "test-multimodal-session",
            "image": img_b64,
            "audio": None
        })

    @sio.on("message_stream")
    async def on_message_stream(data):
        token = data.get("chunk", "")
        tokens.append(token)
        # print(token, end="", flush=True) 

    @sio.on("message_complete")
    async def on_message_complete(data):
        full_response = "".join(tokens)
        print("\n\n--- [BOT RESPONSE] ---\n")
        print(full_response)
        print("\n--- [END RESPONSE] ---\n")
        print("[CLIENT] Generation complete.")
        response_received.set()

    @sio.on("error")
    async def on_error(data):
        print(f"\n[CLIENT] Error: {data}")
        response_received.set()

    try:
        await sio.connect(SERVER_URL, auth={'token': token})
        await asyncio.wait_for(response_received.wait(), timeout=60.0)
        
        print("\n" + "="*50)
        print("SUCCESS: Multimodal flow verified via script.")
        print("="*50)

    except Exception as e:
        print(f"\n[CLIENT] Error: {str(e)}")
    finally:
        await sio.disconnect()

if __name__ == "__main__":
    asyncio.run(test_multimodal_flow())
