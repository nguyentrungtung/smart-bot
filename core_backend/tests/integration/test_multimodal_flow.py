"""
Integration tests for the multimodal (image/audio) processing pipeline.

Tests verify:
1. Image processing builds correct image_url block with size validation
2. Audio processing uses STT pipeline → text block (not raw input_audio)
3. Capabilities detection handles prefixed model names (openai/gemini-2.0-flash)
4. vision_scrubber only processes messages with raw multimodal data
5. vision_scrubber runs AFTER agent (not from START) via should_continue routing
6. format_message_content returns plain string when no attachments
"""
import pytest
import base64
from unittest.mock import AsyncMock, MagicMock, patch
from langchain_core.messages import HumanMessage, AIMessage

from app.multimodal.processor import MultimodalProcessor, _MAX_IMAGE_B64_BYTES
from app.multimodal.capabilities import detect_capabilities, get_capabilities
from app.workflows.nodes.vision_scrubber import scrub_multimodal_content
from app.workflows.graph import should_continue, _should_run_profile_analyzer


# ─── Helpers ────────────────────────────────────────────────────────────────

def _make_small_image_b64() -> str:
    """A minimal valid 1×1 white JPEG in base64 (~100 bytes)."""
    raw = (
        b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00"
        b"\xff\xdb\x00C\x00\x08\x06\x06\x07\x06\x05\x08\x07\x07\x07\t\t"
        b"\x08\n\x0c\x14\r\x0c\x0b\x0b\x0c\x19\x12\x13\x0f\x14\x1d\x1a"
        b"\x1f\x1e\x1d\x1a\x1c\x1c $.' \",#\x1c\x1c(7),01444\x1f'9=82<.342\x1e\xc0"
        b"\x00\x0b\x08\x00\x01\x00\x01\x01\x01\x11\x00\xff\xc4\x00\x1f\x00"
        b"\x00\x01\x05\x01\x01\x01\x01\x01\x01\x00\x00\x00\x00\x00\x00\x00"
        b"\x00\x01\x02\x03\x04\x05\x06\x07\x08\t\n\x0b\xff\xda\x00\x08\x01"
        b"\x01\x00\x00?\x00\xfb\xff\xd9"
    )
    return base64.b64encode(raw).decode()


def _make_audio_b64() -> str:
    """Minimal fake webm audio base64."""
    return base64.b64encode(b"\x1a\x45\xdf\xa3" + b"\x00" * 100).decode()


# ─── 1. capabilities.py ─────────────────────────────────────────────────────

def test_capabilities_gemini_via_openai_prefix():
    """Model 'openai/gemini-2.0-flash' should detect vision+audio (contains 'gemini')."""
    caps = detect_capabilities("openai/gemini-2.0-flash")
    assert caps["vision"] is True
    assert caps["audio"] is True


def test_capabilities_gemini_direct():
    caps = detect_capabilities("gemini-2.5-pro")
    assert caps["vision"] is True
    assert caps["audio"] is True


def test_capabilities_local_model_no_multimodal():
    """Local LM Studio model should have no vision/audio support."""
    caps = detect_capabilities("lm-studio-model")
    assert caps["vision"] is False
    assert caps["audio"] is False


def test_capabilities_gpt4o_vision_no_audio():
    """GPT-4o supports vision but not audio (not Gemini)."""
    caps = detect_capabilities("gpt-4o")
    assert caps["vision"] is True
    assert caps["audio"] is False


def test_capabilities_env_override_false():
    """MULTIMODAL_ENABLED=False disables everything regardless of model."""
    caps = detect_capabilities("gemini-2.0-flash", env_override=False)
    assert caps["vision"] is False
    assert caps["audio"] is False


def test_capabilities_env_override_true():
    """MULTIMODAL_ENABLED=True enables everything regardless of model."""
    caps = detect_capabilities("lm-studio-model", env_override=True)
    assert caps["vision"] is True
    assert caps["audio"] is True


# ─── 2. process_image ────────────────────────────────────────────────────────

def test_process_image_plain_b64():
    """Plain base64 (no data URI prefix) produces image_url block."""
    b64 = _make_small_image_b64()
    result = MultimodalProcessor.process_image(b64)
    assert result["type"] == "image_url"
    assert "image/jpeg" in result["image_url"]["url"]
    assert b64 in result["image_url"]["url"]


def test_process_image_data_uri():
    """Data URI input preserves original MIME type."""
    b64 = _make_small_image_b64()
    raw = f"data:image/png;base64,{b64}"
    result = MultimodalProcessor.process_image(raw)
    assert result["type"] == "image_url"
    assert "image/png" in result["image_url"]["url"]


def test_process_image_too_large_returns_error_text():
    """Images exceeding the size limit return a user-facing error text block."""
    oversized = "A" * (_MAX_IMAGE_B64_BYTES + 1)
    result = MultimodalProcessor.process_image(oversized)
    assert result["type"] == "text"
    assert "quá lớn" in result["text"]


# ─── 3. format_message_content (async) ──────────────────────────────────────

@pytest.mark.asyncio
async def test_format_text_only():
    """Text-only input returns a plain string (no blocks)."""
    result = await MultimodalProcessor.format_message_content(
        text="Xin chào", attachments={}
    )
    assert result == "Xin chào"


@pytest.mark.asyncio
async def test_format_with_image_vision_enabled():
    """With vision enabled, image attachment produces a list with image_url block."""
    b64 = _make_small_image_b64()
    with patch("app.multimodal.processor.get_capabilities", return_value={"vision": True, "audio": False}):
        result = await MultimodalProcessor.format_message_content(
            text="Đây là gì?", attachments={"image": b64}
        )
    assert isinstance(result, list)
    types = [b["type"] for b in result]
    assert "text" in types
    assert "image_url" in types


@pytest.mark.asyncio
async def test_format_with_image_vision_disabled():
    """With vision disabled, image attachment is replaced with warning text."""
    b64 = _make_small_image_b64()
    with patch("app.multimodal.processor.get_capabilities", return_value={"vision": False, "audio": False}):
        result = await MultimodalProcessor.format_message_content(
            text="Ảnh này là gì?", attachments={"image": b64}
        )
    # Should be a list or string — no image_url blocks
    if isinstance(result, list):
        assert not any(b.get("type") == "image_url" for b in result)
        assert any("không hỗ trợ" in b.get("text", "") for b in result)
    else:
        assert "không hỗ trợ" in result


@pytest.mark.asyncio
async def test_format_audio_uses_stt_pipeline():
    """
    Audio attachment triggers STT pipeline — result is a text block, NOT input_audio.
    This is the community best practice: model-agnostic, works with local LLMs.
    """
    b64 = _make_audio_b64()
    mock_transcription = "Tôi muốn hỏi về sản phẩm"

    with patch.object(
        MultimodalProcessor, "speech_to_text",
        new=AsyncMock(return_value=mock_transcription)
    ):
        result = await MultimodalProcessor.format_message_content(
            text="", attachments={"audio": b64}
        )

    # Must NOT contain any input_audio blocks
    if isinstance(result, list):
        assert not any(b.get("type") == "input_audio" for b in result)
        # Must contain the transcription as text
        audio_blocks = [b for b in result if b.get("type") == "text" and "Giọng nói" in b.get("text", "")]
        assert audio_blocks, "Expected a [Giọng nói] text block"
        assert mock_transcription in audio_blocks[0]["text"]
    else:
        assert mock_transcription in result


@pytest.mark.asyncio
async def test_format_audio_stt_failure_returns_fallback():
    """When STT fails, a Vietnamese fallback text is returned — no crash."""
    b64 = _make_audio_b64()
    with patch.object(
        MultimodalProcessor, "speech_to_text",
        new=AsyncMock(return_value="[Lỗi chuyển đổi giọng nói]")
    ):
        result = await MultimodalProcessor.format_message_content(
            text="", attachments={"audio": b64}
        )
    if isinstance(result, list):
        assert any("Không thể chuyển đổi" in b.get("text", "") for b in result)
    else:
        assert "Không thể chuyển đổi" in result


@pytest.mark.asyncio
async def test_format_image_and_audio_combined():
    """Combined image + audio produces text (transcription) + image_url blocks."""
    img_b64 = _make_small_image_b64()
    aud_b64 = _make_audio_b64()

    with patch("app.multimodal.processor.get_capabilities", return_value={"vision": True, "audio": True}):
        with patch.object(
            MultimodalProcessor, "speech_to_text",
            new=AsyncMock(return_value="Hãy phân tích ảnh này")
        ):
            result = await MultimodalProcessor.format_message_content(
                text="Phân tích giúp tôi", attachments={"image": img_b64, "audio": aud_b64}
            )

    assert isinstance(result, list)
    block_types = [b["type"] for b in result]
    assert "image_url" in block_types
    # Audio transcription appears as text block
    assert any("Giọng nói" in b.get("text", "") for b in result)
    # No raw audio blocks
    assert "input_audio" not in block_types


# ─── 4. vision_scrubber ──────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_vision_scrubber_replaces_image_with_description():
    """Scrubber replaces a multimodal HumanMessage with text description."""
    b64 = _make_small_image_b64()
    image_block = {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}}
    original_msg = HumanMessage(
        content=[{"type": "text", "text": "Đây là gì?"}, image_block],
        id="msg-001"
    )

    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = "Một bức ảnh màu đỏ với chữ OMFOOD."

    with patch("app.workflows.nodes.vision_scrubber.litellm.acompletion", new=AsyncMock(return_value=mock_response)):
        result = await scrub_multimodal_content({"messages": [original_msg]})

    assert "messages" in result
    replacement = result["messages"][0]
    assert isinstance(replacement, HumanMessage)
    assert isinstance(replacement.content, str)
    assert "[MÔ TẢ ĐA PHƯƠNG TIỆN]" in replacement.content
    assert "OMFOOD" in replacement.content
    assert replacement.id == "msg-001"
    assert replacement.additional_kwargs.get("scrubbed") is True


@pytest.mark.asyncio
async def test_vision_scrubber_skips_plain_text_messages():
    """Scrubber is a no-op when no multimodal content is present."""
    msg = HumanMessage(content="Xin chào", id="msg-002")
    result = await scrub_multimodal_content({"messages": [msg]})
    assert result == {}


@pytest.mark.asyncio
async def test_vision_scrubber_skips_already_scrubbed():
    """Scrubber skips messages already marked as scrubbed (prevents double-scrub)."""
    msg = HumanMessage(
        content="[MÔ TẢ ĐA PHƯƠNG TIỆN]: một bức ảnh",
        id="msg-003",
        additional_kwargs={"scrubbed": True}
    )
    result = await scrub_multimodal_content({"messages": [msg]})
    assert result == {}


# ─── 5. Graph routing — vision_scrubber after agent ─────────────────────────

def test_should_continue_routes_to_vision_scrubber_for_multimodal():
    """
    After agent generates its final response (no tool calls),
    should_continue must route to vision_scrubber when there is an unprocessed
    multimodal HumanMessage in state.
    """
    b64 = _make_small_image_b64()
    human_msg = HumanMessage(
        content=[
            {"type": "text", "text": "Đây là gì?"},
            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}}
        ],
        id="msg-100"
    )
    ai_msg = AIMessage(content="Đây là ảnh màu đỏ.", id="ai-100")

    state = {
        "messages": [human_msg, ai_msg],
        "summary": "",
        "metadata": {"profile": {}},
        "tool_call_count": 0,
        "session_id": "sess_test",
    }

    result = should_continue(state)
    assert result == "vision_scrubber", (
        f"Expected 'vision_scrubber', got '{result}'. "
        "vision_scrubber must run after agent, not from START."
    )


def test_should_continue_skips_vision_scrubber_for_plain_text():
    """Plain text conversations must NOT route to vision_scrubber."""
    human_msg = HumanMessage(content="Sản phẩm của bạn là gì?", id="msg-200")
    ai_msg = AIMessage(content="Chúng tôi cung cấp...", id="ai-200")

    state = {
        "messages": [human_msg, ai_msg],
        "summary": "",
        "metadata": {"profile": {}},
        "tool_call_count": 0,
        "session_id": "sess_test",
    }

    result = should_continue(state)
    assert result != "vision_scrubber"


def test_should_continue_skips_already_scrubbed_messages():
    """Messages with scrubbed=True in additional_kwargs must not re-trigger scrubber."""
    human_msg = HumanMessage(
        content="[MÔ TẢ ĐA PHƯƠNG TIỆN]: ảnh màu đỏ",
        id="msg-300",
        additional_kwargs={"scrubbed": True}
    )
    ai_msg = AIMessage(content="Tôi thấy ảnh.", id="ai-300")

    state = {
        "messages": [human_msg, ai_msg],
        "summary": "",
        "metadata": {"profile": {}},
        "tool_call_count": 0,
        "session_id": "sess_test",
    }

    result = should_continue(state)
    assert result != "vision_scrubber"
