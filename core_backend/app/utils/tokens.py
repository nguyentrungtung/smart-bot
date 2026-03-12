import logging

logger = logging.getLogger("token_utils")

def estimate_tokens(messages_or_text) -> float:
    """
    Consolidated token estimation logic (Word count * 1.3).
    Accepts a list of LangChain messages or a raw string.
    """
    if isinstance(messages_or_text, str):
        return len(messages_or_text.split()) * 1.3
    
    # It's a list of messages (LangChain or LiteLLM dicts)
    total_text = ""
    for m in messages_or_text:
        content = ""
        if isinstance(m, dict):
            content = str(m.get("content", ""))
        else:
            content = str(getattr(m, "content", ""))
        total_text += content + " "
    
    return len(total_text.split()) * 1.3
