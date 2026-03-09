import pytest
from app.middleware.pii_scrubber import scrub_pii

def test_scrub_email():
    """Assert emails are masked successfully"""
    text = "Vui lòng liên hệ tôi qua email admin@example.com nhé."
    scrubbed = scrub_pii(text)
    assert scrubbed == "Vui lòng liên hệ tôi qua email [REDACTED_EMAIL] nhé."

def test_scrub_phone():
    """Assert Vietnam and common phone numbers are masked"""
    text1 = "SĐT của tôi là 0912345678, gọi đi!"
    scrubbed1 = scrub_pii(text1)
    assert scrubbed1 == "SĐT của tôi là [REDACTED_PHONE], gọi đi!"
    
    # International VN pattern
    text2 = "Liên hệ +84988111222 để biết thêm"
    assert scrub_pii(text2) == "Liên hệ [REDACTED_PHONE] để biết thêm"

def test_scrub_credit_card():
    """Assert standard 16 digit credit cards are caught"""
    text = "Thanh toán bằng thẻ 4111 2222 3333 4444 nha."
    # 16 digits block spaces mask
    scrubbed = scrub_pii(text)
    assert "[REDACTED_CARD]" in scrubbed
    assert "4111" not in scrubbed
