"""
Stream Handler for LiteLLM responses.
Handles both streaming and non-streaming responses,
including <thinking> tag parsing and Socket.IO emission.
"""
import re
import json
import logging
from typing import Any
from langchain_core.messages import AIMessage

logger = logging.getLogger("stream_handler")

# Local models (LM Studio / llama.cpp) leak raw tool-call tokens into content.
# These must be stripped before sending to the client.
_TOOL_LEAK_PATTERN = re.compile(
    r'<\|?tool_call\|?>.*?(?:<\|?/tool_call\|?>|$)'      # <tool_call|>...</tool_call|>
    r'|<tool_response>.*?(?:</tool_response>|$)'           # <tool_response>...</tool_response>
    r'|<\|tool_call_id\|>.*?(?:<\|/tool_call_id\|>|$)',   # <|tool_call_id|>...</|tool_call_id|>
    re.DOTALL
)

# Minimum buffer size before flushing to socket — batches tiny chunks
# from slow local models to reduce socket event count.
_STREAM_FLUSH_SIZE = 12  # chars


def parse_thinking_tags(content: str) -> tuple[str, str]:
    """
    Split content into (thinking_text, clean_text).
    Returns (thought, clean_content) where thought may be empty.
    """
    if "<thinking>" in content and "</thinking>" in content:
        thought = content.split("<thinking>")[1].split("</thinking>")[0]
        clean = content.replace(f"<thinking>{thought}</thinking>", "").strip()
        return thought, clean
    return "", content


async def handle_nonstreaming(
    response: Any,
    sio: Any | None,
    sid: str | None,
) -> AIMessage:
    """Handle a non-streaming LiteLLM response (used for multimodal)."""
    logger.debug(f"DEBUG: Entering handle_nonstreaming for sid={sid}")
    full_content = response.choices[0].message.content or ""
    logger.info(f"Non-streaming response: {len(full_content)} chars")

    if sio and sid and full_content:
        thought, clean = parse_thinking_tags(full_content)
        if thought:
            await sio.emit("thought_stream", {"content": thought}, room=sid)
        await sio.emit("message_stream", {"chunk": clean}, room=sid)
        full_content = clean
    elif not full_content:
        logger.warning(f"Empty content for sid={sid}")

    # Calculate tokens for the final response
    from app.utils.tokens import calculate_tokens
    token_count = calculate_tokens(full_content)

    return AIMessage(
        content=full_content,
        additional_kwargs={"token_count": token_count}
    )


async def handle_streaming(
    response: Any,
    sio: Any | None,
    sid: str | None,
) -> AIMessage:
    """Handle a streaming LiteLLM response with thinking tag detection."""
    logger.debug(f"DEBUG: Entering handle_streaming for sid={sid}")
    full_content = ""
    buffer = ""
    in_thinking = False
    tool_calls_acc: list[dict] = []
    chunk_count = 0

    async for chunk in response:
        chunk_count += 1
        delta = chunk.choices[0].delta
        if chunk_count % 10 == 1:
            logger.debug(f"DEBUG: Received chunk {chunk_count} for sid={sid}")

        # --- Tool calls accumulation ---
        if hasattr(delta, "tool_calls") and delta.tool_calls:
            _accumulate_tool_calls(delta.tool_calls, tool_calls_acc)

        # --- Native reasoning_content (DeepSeek) ---
        if hasattr(delta, "reasoning_content") and delta.reasoning_content:
            if sio and sid:
                await sio.emit("thought_stream", {"content": delta.reasoning_content}, room=sid)
            full_content += delta.reasoning_content
            continue

        # --- Regular content with thinking tag parsing ---
        piece = delta.content or ""
        if not piece:
            continue

        full_content += piece
        buffer += piece

        # Detect <thinking> open
        if "<thinking>" in buffer and not in_thinking:
            pre, rest = buffer.split("<thinking>", 1)
            if pre and sio and sid:
                await sio.emit("message_stream", {"chunk": pre}, room=sid)
            buffer = rest
            in_thinking = True

        if in_thinking:
            if "</thinking>" in buffer:
                think_part, rest = buffer.split("</thinking>", 1)
                if think_part and sio and sid:
                    from app.config.settings import settings
                    if settings.LOG_LEVEL.upper() == "DEBUG":
                        logger.debug(f"[AI THINKING]: {think_part}")
                    await sio.emit("thought_stream", {"content": think_part}, room=sid)
                buffer = rest
                in_thinking = False
                if buffer and sio and sid:
                    await sio.emit("message_stream", {"chunk": buffer}, room=sid)
                    buffer = ""
            else:
                # Keep last 11 chars to detect closing tag across chunks
                THINK_TAG_LEN = 11
                if len(buffer) > _STREAM_FLUSH_SIZE + THINK_TAG_LEN:
                    safe = buffer[:-(THINK_TAG_LEN)]
                    if sio and sid:
                        await sio.emit("thought_stream", {"content": safe}, room=sid)
                    buffer = buffer[-(THINK_TAG_LEN):]
        else:
            # Keep last 10 chars to detect opening/closing tags across chunks.
            # Only flush when we have enough content to make emit worthwhile.
            MSG_TAG_LEN = 10
            if len(buffer) > _STREAM_FLUSH_SIZE + MSG_TAG_LEN:
                safe = buffer[:-(MSG_TAG_LEN)]
                # Strip any embedded tool-call leak tokens before emitting.
                # Using sub() handles partial tokens that span multiple chunks
                # (fullmatch would only catch chunks that are *entirely* a token).
                safe = _TOOL_LEAK_PATTERN.sub("", safe).strip()
                if safe and sio and sid:
                    await sio.emit("message_stream", {"chunk": safe}, room=sid)
                buffer = buffer[-(MSG_TAG_LEN):]

    # Flush remaining buffer
    if buffer:
        if in_thinking and sio and sid:
            await sio.emit("thought_stream", {"content": buffer}, room=sid)
        elif sio and sid:
            clean_buf = _TOOL_LEAK_PATTERN.sub("", buffer).strip()
            if clean_buf:
                await sio.emit("message_stream", {"chunk": clean_buf}, room=sid)

    logger.info(f"Streaming done: {chunk_count} chunks, {len(full_content)} chars total, tool_calls={len(tool_calls_acc)}")

    if chunk_count == 0:
        logger.warning(f"handle_streaming: received 0 chunks for sid={sid}. Model returned empty stream.")

    # Build AIMessage
    last_chunk = locals().get("chunk")
    usage = getattr(last_chunk, "usage", None) if last_chunk is not None else None
    token_count = 0
    if usage:
        token_count = getattr(usage, "total_tokens", 0)
    else:
        # Fallback if usage is not in chunk (some providers don't send it in stream)
        token_count = int(len(full_content.split()) * 1.4)

    # Strip thinking tags and local-model tool-call token leaks from final content
    clean = re.sub(r"<thinking>.*?</thinking>", "", full_content, flags=re.DOTALL)
    clean = _TOOL_LEAK_PATTERN.sub("", clean).strip()
    ai_msg = AIMessage(
        content=clean or full_content,
        additional_kwargs={"token_count": token_count}
    )

    if tool_calls_acc:
        ai_msg.tool_calls = _finalize_tool_calls(tool_calls_acc)

    return ai_msg


# ── Private helpers ──────────────────────────────────────────

def _accumulate_tool_calls(
    delta_tcs: list,
    acc: list[dict],
) -> None:
    """Accumulate streamed tool call fragments.

    NOTE: Only the FIRST chunk for a given index carries the tool call ID.
    Subsequent chunks carry name/argument deltas but repeat the same ID.
    We must NOT concatenate the ID across chunks — only capture it once.
    """
    for tc in delta_tcs:
        if tc.index >= len(acc):
            # First chunk for this tool call — capture ID here and only here.
            acc.append({
                "id": tc.id or f"call_{tc.index}",
                "function": {
                    "name": tc.function.name or "",
                    "arguments": tc.function.arguments or "",
                },
            })
        else:
            # Subsequent chunks — append name/args deltas, IGNORE id (already set).
            if tc.function.name:
                acc[tc.index]["function"]["name"] += tc.function.name
            if tc.function.arguments:
                acc[tc.index]["function"]["arguments"] += tc.function.arguments


def _finalize_tool_calls(acc: list[dict]) -> list[dict]:
    """Parse accumulated tool call JSON arguments into dicts."""
    result = []
    for tc in acc:
        try:
            args = json.loads(tc["function"]["arguments"]) if tc["function"]["arguments"] else {}
        except json.JSONDecodeError:
            args = {}
        result.append({
            "name": tc["function"]["name"],
            "args": args,
            "id": tc["id"],
        })
    return result
