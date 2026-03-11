import socketio
import asyncio
import time

# Socket.IO client setup
URL = "http://localhost:8000"
TOKEN = "..." # Need a valid JWT token

import base64

# Read real image
with open("scripts/test_img.png", "rb") as f:
    B64_IMG = f"data:image/png;base64,{base64.b64encode(f.read()).decode()}"

async def test_socket_multimodal():
    sio = socketio.AsyncClient()
    
    # 1. Get token from login (guest)
    import httpx
    async with httpx.AsyncClient() as client:
        resp = await client.post(f"{URL}/auth/login", json={"user_id": "test-multimodal-user"})
        token = resp.json()["access_token"]

    @sio.event
    async def connect():
        print("Connected to Socket.IO")

    @sio.on("message_stream")
    def on_message(data):
        print(f"[STREAM] {data['chunk']}", end="", flush=True)

    @sio.on("message_complete")
    def on_complete(data):
        print("\n[COMPLETE]")
        asyncio.create_task(sio.disconnect())

    @sio.on("error")
    def on_error(data):
        print(f"[ERROR] {data}")

    await sio.connect(URL, auth={"token": token})
    
    payload = {
        "session_id": "test-session-123",
        "content": "Hello, how are you?",
    }
    
    print("Sending multimodal message...")
    await sio.emit("message", payload)
    
    await sio.wait()

if __name__ == "__main__":
    asyncio.run(test_socket_multimodal())
