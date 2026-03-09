import base64
import logging
from typing import List, Dict, Any, Optional
from app.schemas.socket_io import MessageAttachment

logger = logging.getLogger("multimodal_processor")

class MultimodalProcessor:
    """
    Handles conversion between Socket.IO multimodal payloads and 
    LLM-compatible structures (LiteLLM/OpenAI format).
    """

    @staticmethod
    def process_incoming_attachments(attachments: List[MessageAttachment]) -> List[Dict[str, Any]]:
        """
        Converts MessageAttachments from the widget into LangChain/LiteLLM 
        content blocks.
        """
        blocks = []
        for attachment in attachments:
            if attachment.type == "image":
                # Ensure data is clean (strip prefix if present)
                data = attachment.data
                if "," in data:
                    data = data.split(",")[1]
                
                blocks.append({
                    "type": "image_url",
                    "image_url": {"url": f"data:{attachment.mime_type or 'image/jpeg'};base64,{data}"}
                })
            elif attachment.type == "audio":
                # Audio logic usually requires a separate STT call before hitting the main agent
                # For now, we return a marker that STT is needed
                blocks.append({
                    "type": "audio",
                    "data": attachment.data,
                    "mime_type": attachment.mime_type or "audio/webm"
                })
        return blocks

    @staticmethod
    async def speech_to_text(audio_base64: str) -> str:
        """
        Calls LiteLLM's Whisper endpoint to transcribe audio.
        """
        # Placeholder for actual LiteLLM speech-to-text call
        # Example: litellm.transcription(...)
        logger.info("STT: Transcribing audio chunk...")
        return "[Transcript of audio message]"

    @staticmethod
    async def text_to_speech(text: str) -> bytes:
        """
        Calls LiteLLM's TTS endpoint to convert bot response to audio.
        """
        # Placeholder for actual LiteLLM text-to-speech call
        # Example: litellm.speech(...)
        logger.info("TTS: Synthesizing voice response...")
        return b"MOCK_AUDIO_BINARY_DATA"
