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

    print(f"--- [GENERATE NODE] --- sid={sid}, presence of sio={'YES' if sio else 'NO'}")

    messages = state.get("messages", [])
    metadata = state.get("metadata", {})
    rag_docs = state.get("rag_documents", [])
    summary = state.get("summary", "")

    # ── 1. Guard: bypass check ────────────────────────────────
    if settings.GUARDS_ENABLED:
        fallback = should_bypass(messages, metadata, rag_docs)
        if fallback is not None:
            if sio and sid:
                await sio.emit("message_stream", {"chunk": fallback.content}, room=sid)
                await sio.emit("message_complete", {"session_id": state.get("session_id")}, room=sid)
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
    
    # Token Trimming logic (Layer 4)
    from app.utils.tokens import estimate_tokens
    
    initial_tokens = estimate_tokens(messages)
    logger.info(f"TRIMMER: Initial token estimate: {initial_tokens}")

    # Always keep high-level messages, preserve system prompt
    removed_count = 0
    while estimate_tokens(messages) > settings.MAX_HISTORY_TOKENS and len(messages) > 2:
        # Note: Trimming 'messages' (LangChain) because litellm_messages is a derived view
        # In a real scenario, we'd need to update 'state' or at least the local 'messages'
        # For now, let's stick to the existing trimming logic pattern but with optimized counts
        messages.pop(1)
        removed_count += 1
        # Re-convert to keep litellm_messages in sync if needed, 
        # but let's just optimize the existing loop for now.
    
    # Re-build litellm_messages after trimming
    if removed_count > 0:
        litellm_messages = langchain_to_litellm(messages, system_content)
        logger.info(f"TRIMMER: Removed {removed_count} old messages. New estimate: {estimate_tokens(messages)}")

    # ── [TOKEN USAGE DEBUG] ──
    current_tokens = estimate_tokens(messages)
    logger.info(f"""
    --- [TOKEN USAGE DEBUG] ---
    Model: {settings.LLM_MODEL}
    Limit (Config): {settings.MAX_HISTORY_TOKENS}
    Estimated Current (WORM): {current_tokens}
    Reserved for Response: {4096 - current_tokens if current_tokens < 4096 else 0} tokens
    ---------------------------
    """)

    has_multimodal = has_multimodal_user_message(litellm_messages)
    use_tools = TOOLS 
    should_stream = True
    current_model = settings.LLM_MODEL

    logger.info(
        f"LLM call: model={current_model}, multimodal={has_multimodal}, "
        f"stream={should_stream}, tools={'yes' if use_tools else 'no'}"
    )

    # ── 4. Call LiteLLM (via proxy — proxy speaks OpenAI protocol) ─
    try:
        logger.info(
            f"LLM REQUEST: messages={len(litellm_messages)}, "
            f"content_types={[type(m.get('content')).__name__ for m in litellm_messages]}"
        )

        response = await litellm.acompletion(
            model=current_model,
            messages=litellm_messages,
            tools=use_tools,
            tool_choice="auto" if use_tools else None,
            api_base=settings.LITELLM_API_BASE,
            api_key=settings.LITELLM_API_KEY,
            custom_llm_provider="openai",  # Proxy speaks OpenAI protocol
            stream=should_stream,
        )

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
            await sio.emit("message_stream", {"chunk": error_msg.content}, room=sid)
            await sio.emit("message_complete", {"session_id": state.get("session_id")}, room=sid)
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
