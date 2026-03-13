import logging

logger = logging.getLogger("token_utils")

def calculate_tokens(text: str) -> int:
    """
    Calculate tokens for a single string using word-count multiplier.
    WIRM (Write Once): This should be called when creating a message.
    """
    if not text:
        return 0
    return int(len(str(text).split()) * 1.4)

def estimate_tokens(messages_or_text) -> int:
    """
    Consolidated token estimation logic.
    WORM (Read Many): Sums 'token_count' from message metadata if available.
    """
    if isinstance(messages_or_text, str):
        return calculate_tokens(messages_or_text)
    
    # Sum from metadata
    total = 0
    for m in messages_or_text:
        # Support both LangChain objects and LiteLLM dicts
        metadata = getattr(m, "additional_kwargs", {}) if not isinstance(m, dict) else m.get("metadata", {})
        count = metadata.get("token_count")
        
        if count is not None:
            total += count
        else:
            # Fallback if metadata is missing (should not happen after migration)
            content = str(getattr(m, "content", "")) if not isinstance(m, dict) else str(m.get("content", ""))
            total += calculate_tokens(content)
    
    return total
