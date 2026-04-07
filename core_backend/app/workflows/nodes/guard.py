"""
Bypass / Hallucination Guard for the Generate Node.
Decides whether a message should be blocked or forwarded to the LLM.
"""
import logging
from typing import Any
from langchain_core.messages import BaseMessage, AIMessage, ToolMessage
from app.workflows.nodes.tool_defs import BYPASS_KEYWORDS

logger = logging.getLogger("generate_guard")


def detect_multimodal(content: Any) -> bool:
    """Check if a message content contains image_url or input_audio blocks."""
    if not isinstance(content, list):
        return False
    return any(
        block.get("type") in ("image_url", "input_audio")
        for block in content
    )


def extract_text_from_content(content: Any) -> str:
    """Extract plain text from content, whether str or multimodal list."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return next(
            (item["text"] for item in content if item.get("type") == "text"),
            ""
        )
    return ""


def should_bypass(
    messages: list[BaseMessage],
    metadata: dict,
    rag_docs: list[str],
) -> AIMessage | None:
    """
    Returns a fallback AIMessage if the message should be blocked,
    or None if the message should proceed to LLM.

    Rules:
    - Multimodal messages (image/audio) → NEVER bypass
    - Messages matching bypass keywords (greetings, tools) → allow through
    - No RAG context + not a tool/greeting → block with fallback
    """
    if not messages:
        return None

    last_content = messages[-1].content
    last_text = extract_text_from_content(last_content)

    # Multimodal -> always forward to LLM (Gemini Vision/Audio)
    # Only check the CURRENT message — history images should not permanently disable the guard.
    if detect_multimodal(last_content):
        logger.info("Guard: Multimodal content in current message — bypass SKIPPED.")
        return None

    # CRITICAL: If the last message is a Tool result, we MUST let the LLM generate the final answer.
    if isinstance(messages[-1], ToolMessage):
        logger.info(f"Guard: Tool result detected — bypass SKIPPED.")
        return None

    # Check keyword whitelist
    is_whitelisted = any(kw in last_text.lower() for kw in BYPASS_KEYWORDS)
    if is_whitelisted:
        return None

    # If RAG failed (explicitly marked by RAG node) and not whitelisted → block
    # Exception: if the user has a non-empty profile, allow through — the AI can
    # answer questions about user's own context (name, location, preferences) from
    # the injected profile even without matching RAG documents.
    rag_failed = metadata.get("rag_failed", False)
    profile = metadata.get("profile", {})
    has_profile_context = bool(
        profile.get("name") or profile.get("facts") or profile.get("preferences")
    )
    if rag_failed and not is_whitelisted and not has_profile_context:
        logger.warning(f"Guard: Bypass triggered for: {last_text[:30]}...")
        logger.debug(f"Guard: FULL MESSAGE TEXT (truncated): {last_text[:500]}")  # Log more detail
        return AIMessage(
            content="Xin lỗi, tôi chưa rõ tài liệu này. "
                    "Vui lòng để lại SĐT / Email để nhân viên CSKH hỗ trợ bạn."
        )
    if rag_failed and not is_whitelisted and has_profile_context:
        logger.info(f"Guard: RAG failed but user has profile context — allowing through for profile-aware response.")
        logger.debug(f"Guard: FULL MESSAGE TO LLM: {last_text[:500]}")

    return None
