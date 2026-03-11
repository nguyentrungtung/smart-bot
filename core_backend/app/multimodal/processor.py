import base64
import logging
import io
import litellm
from typing import List, Dict, Any, Union
from app.config.settings import settings
from app.multimodal.capabilities import get_capabilities

logger = logging.getLogger("multimodal_processor")

class MultimodalProcessor:
    """
    Standardized Multimodal Processing Unit.
    Consolidates logic from previous managers and utilities.
    """

    @classmethod
    def process_image(cls, raw_image: str) -> Dict[str, Any]:
        """Process image data into an OpenAI/LiteLLM-compatible block."""
        try:
            mime_type = "image/jpeg"
            base64_data = raw_image
            
            if raw_image.startswith("data:"):
                header, base64_data = raw_image.split(",", 1)
                mime_type = header.split(":")[1].split(";")[0]
            
            return {
                "type": "image_url",
                "image_url": {"url": f"data:{mime_type};base64,{base64_data}"}
            }
        except Exception as e:
            logger.error(f"Error processing image: {str(e)}")
            return {"type": "text", "text": "[Lỗi xử lý hình ảnh]"}

    @classmethod
    def process_audio(cls, raw_audio: str) -> Dict[str, Any]:
        """Process audio data into an OpenAI-compatible input_audio block."""
        try:
            mime_type = "audio/webm"
            base64_data = raw_audio
            
            if raw_audio.startswith("data:"):
                header, base64_data = raw_audio.split(",", 1)
                mime_type = header.split(":")[1].split(";")[0]
            
            # Use OpenAI input_audio format which LiteLLM translates for Gemini
            audio_format = mime_type.split("/")[-1] if "/" in mime_type else "webm"
            return {
                "type": "input_audio",
                "input_audio": {
                    "data": base64_data,
                    "format": audio_format
                }
            }
        except Exception as e:
            logger.error(f"Error processing audio: {str(e)}")
            return {"type": "text", "text": "[Lỗi xử lý âm thanh]"}

    @classmethod
    def format_message_content(cls, text: str, attachments: Dict[str, Any]) -> Union[str, List[Dict[str, Any]]]:
        """
        Main entry point for building multimodal content blocks.
        Attachments: {"image": base64_str, "audio": base64_str}
        """
        caps = get_capabilities()
        blocks = []
        
        if text:
            blocks.append({"type": "text", "text": text})

        # Vision support
        if attachments.get("image"):
            if caps.get("vision"):
                blocks.append(cls.process_image(attachments["image"]))
            else:
                logger.warning("VISION: Skip - Capability disabled.")
                blocks.append({"type": "text", "text": "[Model hiện tại không hỗ trợ hình ảnh]"})

        # Audio support
        if attachments.get("audio"):
            if caps.get("audio"):
                blocks.append(cls.process_audio(attachments["audio"]))
            else:
                logger.warning("AUDIO: Skip - Capability disabled.")
                blocks.append({"type": "text", "text": "[Model hiện tại không hỗ trợ giọng nói]"})

        # Result formatting
        if not blocks:
            return text or ""
        if len(blocks) == 1 and blocks[0]["type"] == "text":
            return blocks[0]["text"]
            
        return blocks

    @staticmethod
    async def speech_to_text(audio_base64: str) -> str:
        """Helper for explicit transcription calls if needed."""
        try:
            data = audio_base64.split(",")[-1]
            audio_bytes = base64.b64decode(data)
            audio_file = io.BytesIO(audio_bytes)
            audio_file.name = "audio.webm"

            response = await litellm.atranscription(
                model=getattr(settings, "STT_MODEL", "whisper-1"),
                file=audio_file,
                api_base=settings.LITELLM_URL,
                api_key=settings.LITELLM_KEY
            )
            return response.get("text", "")
        except Exception as e:
            logger.error(f"STT Error: {str(e)}")
            return "[Lối chuyển đổi giọng nói]"
