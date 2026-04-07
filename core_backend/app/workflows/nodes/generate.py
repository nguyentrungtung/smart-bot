"""
Core Generate Node — Orchestrator.
Delegates to: guard, message_converter, stream_handler, tool_defs.
"""
import logging
import litellm
from typing import Dict, Any

from app.workflows.state import GraphState
from app.prompts.templates.advisor import SALES_SYSTEM_PROMPT
from app.config.settings import settings
from app.workflows.nodes.tool_defs import TOOLS
from app.workflows.nodes.guard import should_bypass
from app.workflows.nodes.message_converter import (
    langchain_to_litellm,
    has_multimodal_user_message,
)
from app.workflows.nodes.stream_handler import handle_streaming, handle_nonstreaming
from app.utils.resilience import async_retry
from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableConfig

logger = logging.getLogger("generate_node")


async def generate_response(
    state: GraphState,
    config: RunnableConfig = None,
) -> Dict[str, Any]:
    """
    Core AI generation node.
    1. Guard check (bypass hallucination trap)
    2. Build prompt context
    3. Convert messages
    4. Call LiteLLM (via proxy)
    5. Handle streaming / non-streaming response
    """
    sio = config.get("configurable", {}).get("sio") if config else None
    sid = config.get("configurable", {}).get("sid") if config else None

    logger.debug(f"Generate node: sid={sid}, sio={'present' if sio else 'absent'}")

    messages = state.get("messages", [])
    metadata = state.get("metadata", {})
    rag_docs = state.get("rag_documents", [])
    summary = state.get("summary", "")

    # ── 1. Guard: bypass check ────────────────────────────────
    if settings.GUARDS_ENABLED:
        fallback = should_bypass(messages, metadata, rag_docs)
        if fallback is not None:
            if sio and sid:
                # Only stream content — socket_handler emits message_complete after the agent node.
                # Emitting message_complete here would cause double-emit and bleed into next turn.
                await sio.emit("message_stream", {"chunk": fallback.content}, room=sid)
            return {"messages": [fallback]}
    else:
        logger.info("Guard: GUARDS_ENABLED=False. Skipping bypass check.")

    # ── 2. Build prompt context ───────────────────────────────
    context_str = f"User Profile: {metadata.get('profile', {})}"
    if summary:
        context_str += f"\n\nBản tóm tắt lịch sử cũ: {summary}"
        
    rag_str = "\n".join(f"- {doc}" for doc in rag_docs)
    system_content = (
        SALES_SYSTEM_PROMPT
        .replace("{{context}}", context_str)
        .replace("{{rag_documents}}", rag_str)
    )

    # ── 3. Convert messages & Token Trimming ──────────────────
    litellm_messages = langchain_to_litellm(messages, system_content)
    
    # Token Trimming logic (Layer 4) — O(n) single pass
    from app.utils.tokens import estimate_tokens

    initial_tokens = estimate_tokens(messages)
    logger.info(f"TRIMMER: Initial token estimate: {initial_tokens}")

    if initial_tokens > settings.MAX_HISTORY_TOKENS and len(messages) > 2:
        # Walk from the oldest non-first message forward, accumulating token savings
        # until we drop below the limit. Always keep messages[0] (first turn context).
        running_total = initial_tokens
        keep_from = 1  # index of first message we will keep after messages[0]
        for i in range(1, len(messages) - 1):  # never drop the last message
            if running_total <= settings.MAX_HISTORY_TOKENS:
                break
            running_total -= estimate_tokens([messages[i]])
            keep_from = i + 1

        removed_count = keep_from - 1
        if removed_count > 0:
            messages = [messages[0]] + messages[keep_from:]
            litellm_messages = langchain_to_litellm(messages, system_content)
            logger.info(
                f"TRIMMER: Removed {removed_count} old messages. "
                f"New estimate: {estimate_tokens(messages)}"
            )

    # ── [TOKEN USAGE DEBUG] ──
    current_tokens = estimate_tokens(messages)
    logger.info(f"""
    --- [TOKEN USAGE DEBUG] ---
    Model: {settings.LLM_MODEL}
    Limit (History): {settings.MAX_HISTORY_TOKENS}
    Estimated Current (WORM): {current_tokens}
    Reserved for Response (MAX): {settings.MAX_RESPONSE_TOKENS} tokens
    ---------------------------
    """)

    has_multimodal = has_multimodal_user_message(litellm_messages)
    should_stream = True

    # Skip tool injection for short social/greeting messages to save tokens
    # and prevent smaller local models from spurious tool calls.
    from app.workflows.nodes.tool_defs import BYPASS_KEYWORDS
    last_user_text = ""
    for m in reversed(litellm_messages):
        if m.get("role") == "user":
            c = m.get("content", "")
            last_user_text = c if isinstance(c, str) else next(
                (b.get("text", "") for b in c if isinstance(b, dict) and b.get("type") == "text"), ""
            )
            break
    _is_social = (
        len(last_user_text.split()) <= 5
        and any(kw in last_user_text.lower() for kw in BYPASS_KEYWORDS)
    )
    use_tools = None if _is_social else TOOLS
    current_model = settings.LLM_MODEL

    logger.info(
        f"[{state.get('interaction_id')}] LLM call: model={current_model}, multimodal={has_multimodal}, "
        f"stream={should_stream}, tools={'yes' if use_tools else 'no'}"
    )

    # Log FULL message content for debugging voice/audio
    logger.info(f"FULL_MESSAGES_TO_LLM: {len(litellm_messages)} messages total")
    for i, m in enumerate(litellm_messages):
        role = m['role'].upper()
        content = m['content']
        if isinstance(content, str):
            logger.info(f"  [{i}] {role}: {content[:500]}")  # Log first 500 chars
        elif isinstance(content, list):
            logger.info(f"  [{i}] {role} (multimodal list with {len(content)} blocks):")
            for j, block in enumerate(content):
                if isinstance(block, dict):
                    block_type = block.get("type", "unknown")
                    if block_type == "text":
                        logger.info(f"      [block {j}] TEXT: {block.get('text', '')[:300]}")
                    else:
                        logger.info(f"      [block {j}] {block_type.upper()}: {str(block)[:100]}")

    if settings.LOG_LEVEL.upper() == "DEBUG":
        logger.debug(f"SYSTEM PROMPT:\n{system_content}")
        for i, m in enumerate(litellm_messages):
            logger.debug(f"  [{i}] {m['role'].upper()}: {str(m['content'])[:200]}...")

    # ── 4. Call LiteLLM (via proxy — proxy speaks OpenAI protocol) ─
    try:
        logger.info(
            f"LLM REQUEST: messages={len(litellm_messages)}, "
            f"content_types={[type(m.get('content')).__name__ for m in litellm_messages]}"
        )

        # Define the call as a local function to apply the retry decorator
        @async_retry(retries=settings.LITELLM_RETRY_COUNT, delay=1.0)
        async def call_llm():
            return await litellm.acompletion(
                model=current_model,
                messages=litellm_messages,
                tools=use_tools,
                tool_choice="auto" if use_tools else None,
                api_base=settings.LITELLM_API_BASE,
                api_key=settings.LITELLM_API_KEY,
                custom_llm_provider="openai",
                stream=should_stream,
                max_tokens=settings.MAX_RESPONSE_TOKENS,
            )

        response = await call_llm()

        # ── 5. Handle response ────────────────────────────────
        if should_stream:
            ai_msg = await handle_streaming(response, sio, sid)
        else:
            ai_msg = await handle_nonstreaming(response, sio, sid)

        logger.info(
            f"LLM RESPONSE: content_len={len(ai_msg.content)}, "
            f"tool_calls={len(ai_msg.tool_calls) if hasattr(ai_msg, 'tool_calls') and ai_msg.tool_calls else 0}"
        )

        return {"messages": [ai_msg]}

    except Exception as e:
        logger.error(f"LiteLLM Error caught in node: {e}")
        error_msg = _build_error_message(has_multimodal)
        if sio and sid:
            # Only stream content — socket_handler emits message_complete after the agent node.
            await sio.emit("message_stream", {"chunk": error_msg.content}, room=sid)
        return {"messages": [error_msg]}


def _build_error_message(has_multimodal: bool) -> AIMessage:
    """Build a user-facing error AIMessage (sync — no I/O)."""
    if has_multimodal:
        text = (
            "Dường như có lỗi khi xử lý hình ảnh hoặc giọng nói (Gemini). "
            "Vui lòng kiểm tra lại định dạng tệp hoặc thử lại sau ít phút."
        )
    else:
        text = "Xin lỗi, hệ thống đang gặp sự cố kỹ thuật khi kết nối với mô hình AI."
    return AIMessage(content=text)
