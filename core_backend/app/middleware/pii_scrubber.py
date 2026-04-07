import re

def scrub_pii(text: str) -> str:
    """
    Sanitizes user input by masking PII (phone, email, credit card, CCCD/CMND)
    before it is sent to LiteLLM or saved to the Conversation Database.
    """
    if not text:
        return text

    # Mask Emails
    email_pattern = r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'
    text = re.sub(email_pattern, '[REDACTED_EMAIL]', text)

    # Mask Vietnamese phone numbers (fixed: use proper character classes, no | inside [])
    # Covers: 03x, 05x, 07x, 08x, 09x series — 10 digits total
    phone_pattern = r'(?:\+84|0)(?:3[2-9]|5[689]|7[06-9]|8[1-589]|9[0-46-9])[0-9]{7}\b'
    text = re.sub(phone_pattern, '[REDACTED_PHONE]', text)

    # Mask Vietnamese CCCD (12 digits) and old CMND (9 digits)
    # Require word boundary and disallow adjacent digits to reduce false positives
    cccd_pattern = r'\b\d{12}\b'
    cmnd_pattern = r'\b\d{9}\b'
    text = re.sub(cccd_pattern, '[REDACTED_ID]', text)
    text = re.sub(cmnd_pattern, '[REDACTED_ID]', text)

    # Mask Credit Cards: 4 groups of 4 digits separated by spaces or dashes (strict format)
    cc_pattern = r'\b\d{4}[ -]\d{4}[ -]\d{4}[ -]\d{4}\b'
    text = re.sub(cc_pattern, '[REDACTED_CARD]', text)

    return text
