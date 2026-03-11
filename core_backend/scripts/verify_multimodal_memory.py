import asyncio
from unittest.mock import AsyncMock, MagicMock
from langchain_core.messages import HumanMessage, AIMessage
from app.workflows.nodes.guard import should_bypass
from app.workflows.nodes.generate import generate_response

async def test_multimodal_context_guard():
    print("Testing Multimodal Context Guard...")
    
    # 1. Message with image
    img_msg = HumanMessage(content=[{"type": "text", "text": "Đây là gì?"}, {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64,..."}}])
    
    # 2. Follow-up text message
    text_msg = HumanMessage(content="Thế còn màu sắc của nó?")
    
    messages = [img_msg, text_msg]
    metadata = {}
    rag_docs = []
    
    # Guard should NOT bypass because history contains media
    fallback = should_bypass(messages, metadata, rag_docs)
    
    assert fallback is None, "Error: Guard bypassed follow-up message despite multimodal history!"
    print("SUCCESS: Guard correctly allowed follow-up message.")

async def test_guard_bypass_emission():
    print("\nTesting Guard Bypass Emission...")
    
    # Unrelated text with no history
    msg = HumanMessage(content="xyz 123 456")
    state = {
        "messages": [msg],
        "metadata": {"rag_failed": True},
        "rag_documents": [],
        "session_id": "test_session"
    }
    
    mock_sio = AsyncMock()
    mock_sid = "test_sid"
    config = {"configurable": {"sio": mock_sio, "sid": mock_sid}}
    
    # Invoke generate_response which triggers guard
    with MagicMock() as mock_graph: # generate_response calls should_bypass internally
        result = await generate_response(state, config)
        
    # Check if socket events were emitted
    emits = [call.args[0] for call in mock_sio.emit.call_args_list]
    print(f"Emitted events: {emits}")
    
    assert "message_stream" in emits, "Error: message_stream not emitted on guard bypass!"
    assert "message_complete" in emits, "Error: message_complete not emitted on guard bypass!"
    print("SUCCESS: Guard bypass correctly emitted socket events.")

if __name__ == "__main__":
    asyncio.run(test_multimodal_context_guard())
    asyncio.run(test_guard_bypass_emission())
