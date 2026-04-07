from gtts import gTTS
import os

texts = [
    "Xin chào, bạn là ai?",
    "Mấy giờ rồi?",
    "Thời tiết Hà Nội hôm nay thế nào?",
    "Smart-Bot có hỗ trợ Zalo không?",
    "Tôi tên là Lâm, tôi ở Sài Gòn. Bạn nhớ nhé.",
    "Bạn có nhớ tên tôi không?",
    "Tóm tắt lại tính năng của Smart-Bot.",
    "Cảm ơn, tạm biệt."
]

for i, text in enumerate(texts):
    tts = gTTS(text, lang='vi')
    tts.save(f"audio_{i+1}.mp3")
    print(f"Generated audio_{i+1}.mp3")
