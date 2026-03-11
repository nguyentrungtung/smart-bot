import asyncio
import socketio
import uuid
import time
import requests

sio = socketio.AsyncClient()

session_id = f"test-stream-{uuid.uuid4().hex[:6]}"
chunk_count = 0
thought_count = 0
start_time = 0

response_received = asyncio.Event()

@sio.event
async def connect():
    print("✅ Connected to Socket.IO server")

@sio.on('message_stream')
async def on_message_stream(data):
    global chunk_count
    chunk_count += 1
    chunk = data.get('chunk', '')
    print(f"📝 MSG CHUNK [{chunk_count}]: {repr(chunk)}")

@sio.on('thought_stream')
async def on_thought_stream(data):
    global thought_count
    thought_count += 1
    content = data.get('content', '')
    print(f"🧠 THOUGHT CHUNK [{thought_count}]: {repr(content)}")

@sio.on('message_complete')
async def on_message_complete(data):
    global start_time, chunk_count, thought_count
    duration = time.time() - start_time
    print(f"\n🏁 Stream complete. Received {chunk_count} message chunks and {thought_count} thought chunks in {duration:.2f}s.")
    response_received.set()

from pathlib import Path
from cryptography.hazmat.primitives import serialization
import jwt

def get_test_token():
    priv_path = Path(".keys/private_key.pem")
    priv = priv_path.read_text()
    token = jwt.encode(
        {"sub": "test_user_123", "iat": int(time.time()), "exp": int(time.time()) + 3600},
        priv,
        algorithm="RS256"
    )
    return token

async def main():
    try:
        global start_time
        token = get_test_token()
        await sio.connect('http://localhost:8000', auth={'token': token})
        
        start_time = time.time()
        prompt = "Please write a 200-word essay about the importance of water. Include a <thinking> process if you can."
        print(f"--- Sending Prompt: {prompt} ---")
        await sio.emit('message', {'session_id': session_id, 'content': prompt})
        
        await asyncio.wait_for(response_received.wait(), timeout=60)
    except Exception as e:
        print(f"❌ Connection failed: {e}")
    finally:
        await sio.disconnect()

if __name__ == '__main__':
    asyncio.run(main())
