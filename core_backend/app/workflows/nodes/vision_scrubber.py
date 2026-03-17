import logging
import litellm
from typing import Dict, Any, List
from langchain_core.messages import HumanMessage, BaseMessage
from app.workflows.state import GraphState
from app.config.settings import settings

logger = logging.getLogger("vision_scrubber")

async def scrub_multimodal_content(state: GraphState) -> Dict[str, Any]:
    """
    Background-capable node that detects base64 images/audio in history
    and replaces them with text descriptions to save tokens in future turns.
    """
    with open("vision_scrubber_debug.log", "a", encoding="utf-8") as f:
        f.write(f"VISION_SCRUBBER: Checking state...\n")
    
    messages = state.get("messages", [])
    if not messages:
        return {}

    updated_messages = []
    
    # We only care about messages in the current history that haven't been scrubbed.
    # Typically, it's the latest HumanMessage.
    for i, msg in enumerate(messages):
        # Flexible type checking (supports class or dict)
        role = getattr(msg, "type", None) or (msg.get("type") if isinstance(msg, dict) else None)
        content = getattr(msg, "content", None) or (msg.get("content") if isinstance(msg, dict) else None)
        
        with open("vision_scrubber_debug.log", "a", encoding="utf-8") as f:
            f.write(f"MSG {i}: type={role}, content_type={type(content).__name__}\n")

        # We only scrub HumanMessages that have list content (multimodal)
        if role == "human" and isinstance(content, list):
            
            # Check if it contains raw data blocks
            has_raw_data = any(
                block.get("type") in ["image_url", "input_audio"] 
                for block in content if isinstance(block, dict)
            )
            
            if has_raw_data:
                msg_id = getattr(msg, "id", None) or (msg.get("id") if isinstance(msg, dict) else None)
                with open("vision_scrubber_debug.log", "a", encoding="utf-8") as f:
                    f.write(f"VISION_SCRUBBER: Found raw data in msg {msg_id}\n")
                
                logger.info(f"SCRUBBER: Detected raw multimodal data in message {msg_id or 'unknown'}")
                
                # Extract any existing text to preserve context
                original_text = ""
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "text":
                        original_text += block.get("text", "")

                try:
                    # Request short description/transcription from LLM
                    # We use a system prompt that encourages a factual description.
                    scrub_prompt = (
                        "Bạn là hệ thống xử lý hậu kỳ. Nhiệm vụ của bạn là xem hình ảnh hoặc nghe âm thanh được cung cấp "
                        "và chuyển đổi nó thành một đoạn văn bản mô tả chi tiết nhưng súc tích (khoảng 2-4 câu). "
                        "Mô tả này sẽ thay thế dữ liệu gốc để tiết kiệm bộ nhớ. Hãy ghi lại các thực thể, màu sắc, văn bản trong hình "
                        "hoặc ý chính của âm thanh. Chỉ trả về văn bản mô tả bằng tiếng Việt."
                    )

                    response = await litellm.acompletion(
                        model=settings.LLM_MODEL,
                        messages=[
                            {"role": "system", "content": scrub_prompt},
                            {"role": "user", "content": content} 
                        ],
                        api_base=settings.LITELLM_API_BASE,
                        api_key=settings.LITELLM_API_KEY,
                        custom_llm_provider="openai",
                        max_tokens=300,
                        temperature=0.2
                    )

                    description = response.choices[0].message.content
                    
                    # Construct new text-only content
                    new_content = f"[MÔ TẢ ĐA PHƯƠNG TIỆN]: {description}"
                    if original_text:
                        new_content = f"{original_text.strip()}\n\n{new_content}"

                    # Create replacement message. 
                    # CRITICAL: Must use the same 'id' so add_messages reducer replaces it.
                    # If msg.id is missing, we can't easily target a specific message 
                    # for replacement in checking-pointing, but LangGraph usually ensures IDs.
                    if hasattr(msg, "id") and msg.id:
                        replacement_msg = HumanMessage(
                            content=new_content, 
                            id=msg.id,
                            additional_kwargs={
                                **getattr(msg, "additional_kwargs", {}),
                                "scrubbed": True,
                                "original_type": "multimodal"
                            }
                        )
                        updated_messages.append(replacement_msg)
                        logger.info(f"SCRUBBER: Message {msg.id} prepared for replacement.")
                    else:
                        logger.warning("SCRUBBER: Found multimodal message but it has no ID. Cannot replace in checkpoint.")

                except Exception as e:
                    with open("vision_scrubber_debug.log", "a", encoding="utf-8") as f:
                        f.write(f"SCRUBBER ERROR: {str(e)}\n")
                    logger.error(f"SCRUBBER ERROR: {str(e)}")
                    # Continue to other messages if one fails
                    continue

    if updated_messages:
        logger.info(f"SCRUBBER: Returning {len(updated_messages)} updated messages to state.")
        return {"messages": updated_messages}
    
    return {}
