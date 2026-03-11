import asyncio
import logging
from app.workflows.nodes.generate import generate_response
from langchain_core.messages import HumanMessage

# Mock the logger to see output
logging.basicConfig(level=logging.INFO)

async def test_hallucination_bypass():
    """
    Simulates Scenario B: RAG fails or context is missing.
    Expected: The agent node returns the hardcoded fallback message.
    """
    print("\n--- Testing Scenario B: Hallucination Bypass ---")
    
    # 1. State with RAG Failure
    state_failed = {
        "messages": [HumanMessage(content="Giá sản phẩm đối thủ?")],
        "metadata": {"rag_failed": True},
        "rag_documents": [] # Empty
    }
    
    result = await generate_response(state_failed)
    response_text = result["messages"][0].content
    
    print(f"Input: 'Giá sản phẩm đối thủ?' (rag_failed=True)")
    print(f"Output: '{response_text}'")
    
    assert "Xin lỗi, tôi chưa rõ tài liệu này" in response_text
    print("SUCCESS: Bypass triggered correctly.")

if __name__ == "__main__":
    asyncio.run(test_hallucination_bypass())
