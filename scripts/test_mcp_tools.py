import asyncio
import httpx
import json

async def test_basic_tools_mcp():
    url = "http://localhost:8001"
    headers = {
        "X-API-Key": "dev-secure-mcp-key-123",
        "Content-Type": "application/json"
    }
    
    # 1. Test List Tools
    print("Testing List Tools...")
    # Standard MCP usually uses SSE, but for this test we'll just check if the server is up and responds to /health
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{url}/health")
            print(f"Health check: {resp.status_code} - {resp.json()}")
    except Exception as e:
        print(f"Server not running at {url}? Error: {e}")
        return

    # 2. Test get_weather call via /messages (JSON-RPC)
    print("\nTesting get_weather call...")
    rpc_payload = {
        "jsonrpc": "2.0",
        "method": "tools/call",
        "params": {
            "name": "get_weather",
            "arguments": {"location": "Hanoi"}
        },
        "id": 1
    }
    
    async with httpx.AsyncClient() as client:
        resp = await client.post(f"{url}/messages?session_id=test-session-weather", json=rpc_payload, headers=headers)
        print(f"Status: {resp.status_code}")
        print(f"Response: {resp.text}")

    # 3. Test get_current_time call
    print("\nTesting get_current_time call...")
    rpc_payload["params"]["name"] = "get_current_time"
    rpc_payload["params"]["arguments"] = {"timezone": "Asia/Ho_Chi_Minh"}
    
    async with httpx.AsyncClient() as client:
        resp = await client.post(f"{url}/messages?session_id=test-session-time", json=rpc_payload, headers=headers)
        print(f"Status: {resp.status_code}")
        print(f"Response: {resp.text}")

if __name__ == "__main__":
    asyncio.run(test_basic_tools_mcp())
