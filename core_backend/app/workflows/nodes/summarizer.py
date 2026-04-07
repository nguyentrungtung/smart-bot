import asyncio
import logging
import litellm
from typing import Dict, Any
from app.workflows.state import GraphState
from app.config.settings import settings
from langchain_core.messages import HumanMessage, AIMessage, RemoveMessage

logger = logging.getLogger("summarizer_node")

_SUMMARY_PROMPT = """\
Bạn là chuyên gia tóm tắt hội thoại. Tóm tắt lịch sử cuộc trò chuyện dưới đây \
thành các điểm cốt lõi theo cấu trúc:

1. **Chủ đề chính**: Người dùng đang hỏi/cần gì?
2. **Thông tin đã cung cấp**: Các dữ kiện, yêu cầu cụ thể người dùng đã đề cập.
3. **Kết quả/Quyết định**: Những gì đã được xác nhận hoặc thực hiện.

Giữ bản tóm tắt dưới 300 từ. Không thêm nhận xét hay đánh giá.
Nếu đã có bản tóm tắt cũ, hãy hợp nhất thông tin mới vào thay vì ghi đè.
"""


async def summarize_history(state: GraphState) -> Dict[str, Any]:
    """
    Summarizes older messages to prevent context overflow.
    Keeps the 6 most recent messages for immediate context.
    Triggered when token count exceeds SUMMARY_THRESHOLD.
    Runs as a background node — does not block message_complete.
    """
    messages = state.get("messages", [])
    current_summary = state.get("summary", "")

    from app.utils.tokens import estimate_tokens
    total_tokens = estimate_tokens(messages)

    if total_tokens < settings.SUMMARY_THRESHOLD and len(messages) < settings.MAX_HISTORY_MESSAGES:
        logger.info(f"SUMMARIZER: Below threshold ({total_tokens} tokens). Skipping.")
        return {"summary": current_summary}

    # Keep last 6 messages fresh — summarize everything older
    KEEP_RECENT = 6
    messages_to_summarize = messages[:-KEEP_RECENT] if len(messages) > KEEP_RECENT else []

    if not messages_to_summarize:
        logger.info("SUMMARIZER: Not enough old messages to summarize.")
        return {"summary": current_summary}

    logger.info(
        f"SUMMARIZER: Threshold exceeded ({total_tokens} tokens, {len(messages)} msgs). "
        f"Summarizing {len(messages_to_summarize)} old messages, keeping {KEEP_RECENT} recent."
    )

    history_str = ""
    for m in messages_to_summarize:
        if isinstance(m, HumanMessage):
            role = "User"
        elif isinstance(m, AIMessage):
            role = "Assistant"
        else:
            continue
        if isinstance(m.content, str):
            text = m.content
            label = ""
        elif isinstance(m.content, list):
            # Extract text blocks from multimodal content (image/voice turns)
            has_image = any(b.get("type") == "image_url" for b in m.content if isinstance(b, dict))
            text = " ".join(
                block.get("text", "") for block in m.content
                if isinstance(block, dict) and block.get("type") == "text"
            )
            label = " [đã gửi ảnh]" if has_image else ""
        else:
            text = ""
            label = ""
        if text:
            history_str += f"{role}{label}: {text}\n"

    system_content = _SUMMARY_PROMPT
    if current_summary:
        system_content += f"\n\nBản tóm tắt hiện tại (cần hợp nhất):\n{current_summary}"

    try:
        response = await asyncio.wait_for(
            litellm.acompletion(
                model=settings.LLM_MODEL,
                messages=[
                    {"role": "system", "content": system_content},
                    {"role": "user", "content": f"Lịch sử cần tóm tắt:\n{history_str}"}
                ],
                api_base=settings.LITELLM_API_BASE,
                api_key=settings.LITELLM_API_KEY,
                custom_llm_provider="openai",
                stream=False,
                max_tokens=512,
            ),
            timeout=settings.LLM_TIMEOUT_SECONDS,
        )

        new_summary = response.choices[0].message.content or ""
        logger.info(f"SUMMARIZER: New summary generated ({len(new_summary)} chars).")

        # Remove summarized messages from LangGraph state
        delete_ops = [RemoveMessage(id=m.id) for m in messages_to_summarize if m.id]
        logger.info(f"SUMMARIZER: Removing {len(delete_ops)} old messages from checkpointer.")

        return {
            "summary": new_summary,
            "messages": delete_ops,
        }

    except asyncio.TimeoutError:
        logger.error(f"SUMMARIZER: Timed out after {settings.LLM_TIMEOUT_SECONDS}s. Keeping current summary.")
        return {"summary": current_summary}
    except Exception as e:
        logger.error(f"SUMMARIZER: Error during summarization: {e}")
        return {"summary": current_summary}
