import socketio
import asyncio
import time
import sys

# Constants for testing
SERVER_URL = "http://localhost:8000"
TEST_MESSAGE = "Hello Gemini, can you confirm you are version 2.5 and tell me a short joke?"
DUMMY_TOKEN = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6IkpvaG4gRG9lIiwiaWF0IjoxNTE2MjM5MDIyfQ.Njt4S7T-s-kQ-YI-7I" # Note: Backend uses RS256, but connection requires a 'token' in auth

async def test_e2e_flow():
    sio = socketio.AsyncClient()
    response_received = asyncio.Event()
    tokens = []

    @sio.event
    async def connect():
        print(f"[CLIENT] Connected to server at {SERVER_URL}")
        # Send a message simulated from FE
        print(f"[CLIENT] Sending message: {TEST_MESSAGE}")
        await sio.emit("message", {
            "content": TEST_MESSAGE,
            "session_id": "test-e2e-session",
            "image": None,
            "audio": None
        })

    @sio.on("message_stream")
    async def on_message_stream(data):
        token = data.get("text", "")
        tokens.append(token)
        print(token, end="", flush=True)

    @sio.on("message_stream_end")
    async def on_message_stream_end(data):
        print("\n[CLIENT] Stream ended.")
        response_received.set()

    @sio.on("error")
    async def on_error(data):
        print(f"\n[CLIENT] Error received: {data}")
        response_received.set()

    try:
        # Pass a token in auth to satisfy the connect event check
        await sio.connect(SERVER_URL, auth={'token': DUMMY_TOKEN})
        # Wait for response with timeout
        await asyncio.wait_for(response_received.wait(), timeout=60.0)
        
        full_response = "".join(tokens)
        print("\n" + "="*50)
        print(f"Final Response Length: {len(full_response)}")
        if len(full_response) > 0:
            print("SUCCESS: Received response from Gemini 2.5 via LiteLLM & BE")
        else:
            print("FAILED: Received empty response")
        print("="*50)

    except asyncio.TimeoutError:
        print("\n[CLIENT] Timeout: No response received from server within 60s")
    except Exception as e:
        print(f"\n[CLIENT] Unexpected Error: {str(e)}")
    finally:
        await sio.disconnect()

if __name__ == "__main__":
    print("Starting E2E Socket.IO Flow Test...")
    print("Make sure the backend (port 8000) and LiteLLM Proxy are running.")
    asyncio.run(test_e2e_flow())
