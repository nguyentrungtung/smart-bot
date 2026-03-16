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
    for i, m in enumerate(messages_or_text):
        # Support both LangChain objects and LiteLLM dicts
        metadata = getattr(m, "additional_kwargs", {}) if not isinstance(m, dict) else m.get("metadata", {})
        count = metadata.get("token_count")
        
        chunk_count = 0
        if count is not None:
            chunk_count = count
        else:
            # Fallback if metadata is missing
            content = str(getattr(m, "content", "")) if not isinstance(m, dict) else str(m.get("content", ""))
            chunk_count = calculate_tokens(content)
        
        total += chunk_count
        # logger.debug(f"TOKEN_DEBUG: Msg {i} ({type(m).__name__}) = {chunk_count} tokens")
    
    if total > 5000:
        logger.warning(f"TOKEN_ALERT: Total tokens estimated at {total}! Threshold is usually 1500.")
        
    return total
