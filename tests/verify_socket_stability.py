# tests/verify_socket_stability.py
import socketio
import asyncio
import time
import jwt

# Reuse the sync logic to get a fresh token
from pathlib import Path
from cryptography.hazmat.primitives import serialization

def get_test_token():
    # Relative to project root
    priv_path = Path(".keys/private_key.pem")
    priv = priv_path.read_text()
    token = jwt.encode(
        {"sub": "test_user_123", "iat": int(time.time()), "exp": int(time.time()) + 3600},
        priv,
        algorithm="RS256"
    )
    return token

async def run_test():
    sio = socketio.AsyncClient(logger=True, engineio_logger=True)
    token = get_test_token()
    
    connected = asyncio.Event()
    response_received = asyncio.Event()
    chunks_count = 0

    @sio.on('connect')
    def on_connect():
        print("✅ Script connected to server")
        connected.set()

    @sio.on('disconnect')
    def on_disconnect():
        print("❌ Script disconnected from server")

    @sio.on('message_stream')
    def on_message(data):
        nonlocal chunks_count
        chunks_count += 1
        print(f"📥 Received chunk: {data.get('chunk')}")

    @sio.on('message_complete')
    def on_complete(data):
        print(f"🏁 Response complete for session: {data.get('session_id')}")
        response_received.set()

    @sio.on('error')
    def on_error(data):
        print(f"⚠️ Error from server: {data.get('detail')}")

    print("--- Starting Socket Stability Test ---")
    try:
        await sio.connect("http://localhost:8000", auth={"token": token})
        await asyncio.wait_for(connected.wait(), timeout=10)
        
        # Test Case 1: Simple Greeting
        print("\n--- Test 1: Sending 'xin chào' ---")
        await sio.emit("message", {"session_id": "test-stable-1", "content": "xin chào", "image": None})
        
        await asyncio.wait_for(response_received.wait(), timeout=60)
        print(f"✅ Test 1 Passed. Received {chunks_count} chunks.")
        
        # Keep connection open for a bit to check for stability
        print("\n--- Waiting 5 seconds to check for 'transport close' ---")
        await asyncio.sleep(5)
        
        if sio.connected:
            print("✨ Connection still alive after 5 seconds. STABLE.")
        else:
            print("🚨 Connection lost after response!")

        # Test Case 2: Consecutive messages
        response_received.clear()
        chunks_count = 0
        print("\n--- Test 2: Consecutive message 'hỏi về sản phẩm' ---")
        await sio.emit("message", {"session_id": "test-stable-1", "content": "hỏi về sản phẩm", "image": None})
        await asyncio.wait_for(response_received.wait(), timeout=60)
        print(f"✅ Test 2 Passed.")

    except Exception as e:
        print(f"❌ Test Failed with Exception: {type(e).__name__}: {str(e)}")
    finally:
        await sio.disconnect()
        print("--- Test Finished ---")

if __name__ == "__main__":
    asyncio.run(run_test())
