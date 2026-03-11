"""
Test Suite: Multimodal Guard, Message Converter, Stream Handler
===============================================================
Tests the refactored modules extracted from generate.py.

Run: python -m pytest tests/test_multimodal_bypass.py -v -s
"""
import pytest
import base64
from unittest.mock import patch, AsyncMock, MagicMock
from langchain_core.messages import HumanMessage, AIMessage, ToolMessage


# ============================================================
# TEST: guard.py
# ============================================================
class TestGuard:

    def test_multimodal_image_skips_bypass(self):
        """Image messages NEVER trigger bypass."""
        from app.workflows.nodes.guard import should_bypass

        content = [
            {"type": "text", "text": "anh nay noi ve cai gi"},
            {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64,abc"}}
        ]
        msg = HumanMessage(content=content)
        result = should_bypass([msg], {"rag_failed": True}, [])
        assert result is None, "Multimodal should NOT be bypassed"

    def test_multimodal_audio_skips_bypass(self):
        """Audio messages NEVER trigger bypass."""
        from app.workflows.nodes.guard import should_bypass

        content = [{"type": "input_audio", "input_audio": {"data": "abc", "format": "webm"}}]
        msg = HumanMessage(content=content)
        result = should_bypass([msg], {"rag_failed": True}, [])
        assert result is None, "Audio should NOT be bypassed"

    def test_greeting_skips_bypass(self):
        """Greetings (bypass keywords) skip guard."""
        from app.workflows.nodes.guard import should_bypass

        msg = HumanMessage(content="xin chao")
        result = should_bypass([msg], {"rag_failed": True}, [])
        assert result is None

    def test_offtopic_text_triggers_bypass(self):
        """Off-topic text with no RAG context triggers bypass."""
        from app.workflows.nodes.guard import should_bypass

        msg = HumanMessage(content="con meo keu gi")
        result = should_bypass([msg], {"rag_failed": True}, [])
        assert result is not None
        assert isinstance(result, AIMessage)

    def test_domain_text_with_rag_passes(self):
        """On-topic text WITH RAG context passes through."""
        from app.workflows.nodes.guard import should_bypass

        msg = HumanMessage(content="gia san pham nay bao nhieu")
        result = should_bypass([msg], {"rag_failed": False}, ["Product info here"])
        assert result is None


class TestGuardHelpers:

    def test_detect_multimodal_true(self):
        from app.workflows.nodes.guard import detect_multimodal

        content = [
            {"type": "text", "text": "hi"},
            {"type": "image_url", "image_url": {"url": "data:..."}}
        ]
        assert detect_multimodal(content) is True

    def test_detect_multimodal_false_text_only(self):
        from app.workflows.nodes.guard import detect_multimodal

        assert detect_multimodal("just text") is False
        assert detect_multimodal([{"type": "text", "text": "hi"}]) is False

    def test_extract_text_from_multimodal(self):
        from app.workflows.nodes.guard import extract_text_from_content

        content = [
            {"type": "text", "text": "describe this"},
            {"type": "image_url", "image_url": {"url": "data:..."}}
        ]
        assert extract_text_from_content(content) == "describe this"

    def test_extract_text_from_string(self):
        from app.workflows.nodes.guard import extract_text_from_content

        assert extract_text_from_content("hello world") == "hello world"


# ============================================================
# TEST: message_converter.py
# ============================================================
class TestMessageConverter:

    def test_basic_conversion(self):
        from app.workflows.nodes.message_converter import langchain_to_litellm

        msgs = [HumanMessage(content="hello")]
        result = langchain_to_litellm(msgs, "You are a bot")

        assert len(result) == 2
        assert result[0]["role"] == "system"
        assert result[1]["role"] == "user"
        assert result[1]["content"] == "hello"

    def test_multimodal_preserved(self):
        from app.workflows.nodes.message_converter import langchain_to_litellm

        content = [
            {"type": "text", "text": "describe"},
            {"type": "image_url", "image_url": {"url": "data:image/png;base64,abc"}}
        ]
        msgs = [HumanMessage(content=content)]
        result = langchain_to_litellm(msgs, "system")

        assert isinstance(result[1]["content"], list)
        assert len(result[1]["content"]) == 2

    def test_tool_message_has_tool_call_id(self):
        from app.workflows.nodes.message_converter import langchain_to_litellm

        tool_msg = ToolMessage(content="result", tool_call_id="call_123")
        msgs = [tool_msg]
        result = langchain_to_litellm(msgs, "system")

        assert result[1]["role"] == "tool"
        assert result[1]["tool_call_id"] == "call_123"

    def test_assistant_with_tool_calls(self):
        from app.workflows.nodes.message_converter import langchain_to_litellm

        ai_msg = AIMessage(content="")
        ai_msg.tool_calls = [
            {"id": "call_1", "name": "get_weather", "args": {"location": "HN"}}
        ]
        msgs = [ai_msg]
        result = langchain_to_litellm(msgs, "system")

        assert "tool_calls" in result[1]
        assert result[1]["tool_calls"][0]["function"]["name"] == "get_weather"

    def test_has_multimodal_detection(self):
        from app.workflows.nodes.message_converter import has_multimodal_user_message

        msgs = [
            {"role": "system", "content": "sys"},
            {"role": "user", "content": [
                {"type": "text", "text": "hi"},
                {"type": "image_url", "image_url": {"url": "data:..."}}
            ]}
        ]
        assert has_multimodal_user_message(msgs) is True

        msgs_text = [
            {"role": "system", "content": "sys"},
            {"role": "user", "content": "just text"}
        ]
        assert has_multimodal_user_message(msgs_text) is False


# ============================================================
# TEST: stream_handler.py
# ============================================================
class TestStreamHandler:

    def test_parse_thinking_tags(self):
        from app.workflows.nodes.stream_handler import parse_thinking_tags

        content = "<thinking>I need to think</thinking>Hello user!"
        thought, clean = parse_thinking_tags(content)
        assert thought == "I need to think"
        assert clean == "Hello user!"

    def test_parse_no_thinking(self):
        from app.workflows.nodes.stream_handler import parse_thinking_tags

        thought, clean = parse_thinking_tags("Just a normal message")
        assert thought == ""
        assert clean == "Just a normal message"


# ============================================================
# TEST: tool_defs.py
# ============================================================
class TestToolDefs:

    def test_tools_structure(self):
        from app.workflows.nodes.tool_defs import TOOLS

        assert len(TOOLS) == 3
        names = [t["function"]["name"] for t in TOOLS]
        assert "get_weather" in names
        assert "get_current_time" in names
        assert "create_xweb_instance" in names

    def test_bypass_keywords(self):
        from app.workflows.nodes.tool_defs import BYPASS_KEYWORDS

        assert "xin chào" in BYPASS_KEYWORDS
        assert "hello" in BYPASS_KEYWORDS
        assert "thời tiết" in BYPASS_KEYWORDS


# ============================================================
# TEST: Multimodal Processor (existing module)
# ============================================================
class TestMultimodalProcessor:

    def test_process_image_data_url(self):
        from app.multimodal.processor import MultimodalProcessor

        fake_b64 = base64.b64encode(b"fake").decode()
        block = MultimodalProcessor.process_image(f"data:image/png;base64,{fake_b64}")
        assert block["type"] == "image_url"

    def test_process_audio(self):
        from app.multimodal.processor import MultimodalProcessor

        fake_b64 = base64.b64encode(b"audio").decode()
        block = MultimodalProcessor.process_audio(f"data:audio/webm;base64,{fake_b64}")
        assert block["type"] == "input_audio"
        assert block["input_audio"]["format"] == "webm"

    def test_format_with_image(self):
        from app.multimodal.processor import MultimodalProcessor

        fake_b64 = base64.b64encode(b"img").decode()
        with patch('app.multimodal.processor.get_capabilities', return_value={"vision": True, "audio": True}):
            result = MultimodalProcessor.format_message_content(
                text="describe",
                attachments={"image": f"data:image/jpeg;base64,{fake_b64}", "audio": None}
            )
        assert isinstance(result, list)
        assert len(result) == 2


# ============================================================
# TEST: Capability Detection
# ============================================================
class TestCapabilities:

    def test_gemini_has_vision_audio(self):
        from app.multimodal.capabilities import detect_capabilities

        caps = detect_capabilities("gemini-2.5-flash")
        assert caps["vision"] is True
        assert caps["audio"] is True

    def test_local_no_multimodal(self):
        from app.multimodal.capabilities import detect_capabilities

        caps = detect_capabilities("lm-studio-model")
        assert caps["vision"] is False
        assert caps["audio"] is False

    def test_override_true(self):
        from app.multimodal.capabilities import detect_capabilities

        caps = detect_capabilities("lm-studio-model", env_override=True)
        assert caps["vision"] is True
        assert caps["audio"] is True


# ============================================================
# TEST: E2E Flow Trace (integration logic test)
# ============================================================
class TestE2EFlow:

    def test_image_flow_reaches_llm(self):
        """Trace: image message -> guard passes -> multimodal detected -> would call LLM."""
        from app.workflows.nodes.guard import should_bypass
        from app.workflows.nodes.message_converter import langchain_to_litellm, has_multimodal_user_message
        from app.multimodal.processor import MultimodalProcessor

        # 1. Build multimodal content
        fake_b64 = base64.b64encode(b"real_jpeg_data").decode()
        with patch('app.multimodal.processor.get_capabilities', return_value={"vision": True, "audio": True}):
            content = MultimodalProcessor.format_message_content(
                text="anh nay noi ve cai gi",
                attachments={"image": f"data:image/jpeg;base64,{fake_b64}", "audio": None}
            )

        msg = HumanMessage(content=content)

        # 2. Guard should NOT bypass
        fallback = should_bypass([msg], {"rag_failed": True}, [])
        assert fallback is None, "Guard should let multimodal through"

        # 3. Convert messages
        litellm_msgs = langchain_to_litellm([msg], "system prompt")
        assert has_multimodal_user_message(litellm_msgs) is True

    def test_text_bypass_still_works(self):
        """Off-topic text without RAG should still be blocked."""
        from app.workflows.nodes.guard import should_bypass

        msg = HumanMessage(content="con meo keu gi")
        fallback = should_bypass([msg], {"rag_failed": True}, [])
        assert fallback is not None
        assert "CSKH" in fallback.content


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
