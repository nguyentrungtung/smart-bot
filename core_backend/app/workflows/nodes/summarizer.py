import logging
import litellm
from typing import Dict, Any
from app.workflows.state import GraphState
from app.config.settings import settings
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage

logger = logging.getLogger("summarizer_node")

async def summarize_history(state: GraphState) -> Dict[str, Any]:
    """
    Node that checks message history length and summarizes older messages
    if they exceed a certain threshold to keep the context window manageable.
    """
    messages = state.get("messages", [])
    current_summary = state.get("summary", "")
    
    # Estimate tokens using WORM strategy
    from app.utils.tokens import estimate_tokens
    total_est_tokens = estimate_tokens(messages)
    
    # Only summarize if we are over the threshold
    if total_est_tokens < settings.SUMMARY_THRESHOLD:
        return {"summary": current_summary}

    logger.info(f"SUMMARIZER: Threshold exceeded ({total_est_tokens:.0f} tokens). Generating summary...")

    # We want to summarize the OLDER messages, keeping the last 4 for immediate context
    messages_to_summarize = messages[:-4]
    
    if not messages_to_summarize:
        return {"summary": current_summary}

    summary_prompt = (
        "Bạn là chuyên gia tóm tắt hội thoại. Hãy tóm tắt các điểm chính, "
        "thông tin quan trọng và yêu cầu của người dùng từ lịch sử trò chuyện dưới đây. "
        "Hãy giữ bản tóm tắt ngắn gọn nhưng đầy đủ thông tin thực tế (tên, sở thích, vấn đề đang gặp). "
        "Bản tóm tắt này sẽ được dùng làm ngữ cảnh cho các câu trả lời tiếp theo."
    )
    
    if current_summary:
        summary_prompt += f"\n\nBản tóm tắt hiện tại: {current_summary}"

    history_str = ""
    for m in messages_to_summarize:
        role = "User" if isinstance(m, HumanMessage) else "Assistant"
        history_str += f"{role}: {m.content}\n"

    try:
        response = await litellm.acompletion(
            model=settings.LLM_MODEL,
            messages=[
                {"role": "system", "content": summary_prompt},
                {"role": "user", "content": f"Lịch sử cần tóm tắt:\n{history_str}"}
            ],
            api_base=settings.LITELLM_API_BASE,
            api_key=settings.LITELLM_API_KEY,
            custom_llm_provider="openai",
            stream=False
        )
        
        new_summary = response.choices[0].message.content
        logger.info("SUMMARIZER: New summary generated successfully.")
        
        # TRUNCATION LOGIC:
        # Since we use add_messages reducer, returning RemoveMessage objects 
        # for old messages will delete them from the checkpointer state.
        from langchain_core.messages import RemoveMessage
        delete_ops = []
        for m in messages_to_summarize:
            if m.id:
                delete_ops.append(RemoveMessage(id=m.id))
        
        logger.info(f"SUMMARIZER: Truncating {len(delete_ops)} old messages from state.")
        
        return {
            "summary": new_summary,
            "messages": delete_ops
        }

    except Exception as e:
        logger.error(f"Summarizer Error: {e}")
        return {"summary": current_summary}
