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
                        print(f"--- [AI THINKING] --- {think_part}")
                    await sio.emit("thought_stream", {"content": think_part}, room=sid)
                buffer = rest
                in_thinking = False
                if buffer and sio and sid:
                    await sio.emit("message_stream", {"chunk": buffer}, room=sid)
                    buffer = ""
            else:
                # Flush safe portion of thinking buffer (keep last 11 chars for tag detection)
                if len(buffer) > 11:
                    safe = buffer[:-11]
                    if sio and sid:
                        await sio.emit("thought_stream", {"content": safe}, room=sid)
                    buffer = buffer[-11:]
        else:
            # Flush safe portion of message buffer (keep last 10 chars for tag detection)
            if len(buffer) > 10:
                safe = buffer[:-10]
                if sio and sid:
                    await sio.emit("message_stream", {"chunk": safe}, room=sid)
                buffer = buffer[-10:]

    # Flush remaining buffer
    if buffer:
        if in_thinking and sio and sid:
            await sio.emit("thought_stream", {"content": buffer}, room=sid)
        elif sio and sid:
            await sio.emit("message_stream", {"chunk": buffer}, room=sid)

    logger.info(f"Streaming done: {chunk_count} chunks, {len(full_content)} chars total, tool_calls={len(tool_calls_acc)}")

    # Build AIMessage
    usage = getattr(chunk, "usage", None) if 'chunk' in locals() else None
    token_count = 0
    if usage:
        token_count = getattr(usage, "total_tokens", 0)
    else:
        # Fallback if usage is not in chunk (some providers don't send it in stream)
        token_count = int(len(full_content.split()) * 1.4)

    clean = re.sub(r"<thinking>.*?</thinking>", "", full_content, flags=re.DOTALL).strip()
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
    """Accumulate streamed tool call fragments."""
    for tc in delta_tcs:
        if tc.index >= len(acc):
            acc.append({
                "id": tc.id or f"call_{tc.index}",
                "function": {
                    "name": tc.function.name or "",
                    "arguments": tc.function.arguments or "",
                },
            })
        else:
            if tc.id:
                acc[tc.index]["id"] += tc.id
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
