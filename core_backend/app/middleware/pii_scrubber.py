import re

def scrub_pii(text: str) -> str:
    """
    Sanitizes user input by masking Phone numbers, Emails, and basic Credit Card patterns
    before it is sent to LiteLLM or saved to the Conversation Database.
    """
    if not text:
        return text

    # Mask Emails
    email_pattern = r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'
    text = re.sub(email_pattern, '[REDACTED_EMAIL]', text)

    # Mask Phone Numbers (Basic VN/International patterns, e.g., 0912345678 or +84912345678)
    # This regex is a simplified example
    phone_pattern = r'(?:\+84|0)(?:3[2-9]|5[6|8|9]|7[0|6-9]|8[1-5|8|9]|9[0-4|6-9])[0-9]{7}\b'
    text = re.sub(phone_pattern, '[REDACTED_PHONE]', text)
    
    # Mask Credit Cards (16 digits separated by spaces or dashes)
    cc_pattern = r'\b(?:\d[ -]*){13,16}\b'
    text = re.sub(cc_pattern, '[REDACTED_CARD]', text)

    return text
