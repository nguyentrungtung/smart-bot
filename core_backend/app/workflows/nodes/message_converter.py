"""
LangChain ↔ LiteLLM Message Converter.
Converts between LangChain BaseMessage objects and LiteLLM dict format.
"""
import json
import logging
from typing import Any
from langchain_core.messages import HumanMessage, AIMessage, ToolMessage, BaseMessage

logger = logging.getLogger("message_converter")


def langchain_to_litellm(
    messages: list[BaseMessage],
    system_content: str,
) -> list[dict[str, Any]]:
    """
    Convert LangChain messages to LiteLLM-compatible dict list.
    Preserves multimodal content arrays (image_url/input_audio blocks).
    """
    litellm_msgs: list[dict[str, Any]] = [
        {"role": "system", "content": system_content}
    ]

    for msg in messages:
        role = _resolve_role(msg)

        # Preserve multimodal content arrays as-is for Gemini
        if isinstance(msg.content, list):
            content_value = msg.content
            logger.debug(f"Multimodal message: {len(msg.content)} blocks")
        else:
            content_value = str(msg.content)

        m_dict: dict[str, Any] = {"role": role, "content": content_value}

        # Attach tool_call_id for tool responses
        if role == "tool" and hasattr(msg, "tool_call_id"):
            m_dict["tool_call_id"] = msg.tool_call_id

        # Attach tool_calls for assistant messages
        elif role == "assistant" and getattr(msg, "tool_calls", None):
            m_dict["tool_calls"] = [
                {
                    "id": tc.get("id"),
                    "type": "function",
                    "function": {
                        "name": tc.get("name"),
                        "arguments": json.dumps(tc.get("args")),
                    },
                }
                for tc in msg.tool_calls
            ]

        litellm_msgs.append(m_dict)

    return litellm_msgs


def has_multimodal_user_message(litellm_msgs: list[dict[str, Any]]) -> bool:
    """Check if any user message in the list contains multimodal content."""
    return any(
        isinstance(m["content"], list)
        for m in litellm_msgs
        if m["role"] == "user"
    )


def _resolve_role(msg: BaseMessage) -> str:
    """Map LangChain message type to LiteLLM role string."""
    if isinstance(msg, HumanMessage):
        return "user"
    if isinstance(msg, AIMessage):
        return "assistant"
    if isinstance(msg, ToolMessage):
        return "tool"
    return "system"
