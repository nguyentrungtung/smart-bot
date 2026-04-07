import logging
from typing import List, Dict, Any, Union

from app.multimodal.capabilities import get_capabilities
from app.multimodal.audio_pipeline import process_audio

logger = logging.getLogger("multimodal_processor")

# Max base64 image size: ~5.5 MB (≈ 4 MB raw image). Models reject larger payloads.
_MAX_IMAGE_B64_BYTES = 5_500_000


class MultimodalProcessor:
    """
    Standardized Multimodal Processing Unit.

    Image pipeline (community best practice):
      image_url with data URI → works with OpenAI, Gemini via LiteLLM, Anthropic.

    Audio pipeline (community best practice):
      Server-side STT first (Whisper) → pass transcription text to LLM.
      This is model-agnostic and avoids the input_audio format fragmentation
      between OpenAI Realtime, Gemini Live, and local models.
    """

    @classmethod
    def process_image(cls, raw_image: str) -> Dict[str, Any]:
        """
        Validate and convert image data to an OpenAI/LiteLLM-compatible image_url block.
        Rejects oversized images before they hit the model API.
        """
        try:
            mime_type = "image/jpeg"
            base64_data = raw_image

            if raw_image.startswith("data:"):
                header, base64_data = raw_image.split(",", 1)
                mime_type = header.split(":")[1].split(";")[0]

            # Validate size — reject before sending to model
            if len(base64_data) > _MAX_IMAGE_B64_BYTES:
                logger.warning(
                    f"VISION: Image too large ({len(base64_data):,} chars > {_MAX_IMAGE_B64_BYTES:,} limit). Rejecting."
                )
                return {"type": "text", "text": "[Hình ảnh quá lớn (> 4MB). Vui lòng gửi ảnh nhỏ hơn.]"}

            return {
                "type": "image_url",
                "image_url": {"url": f"data:{mime_type};base64,{base64_data}"}
            }
        except Exception as e:
            logger.error(f"Error processing image: {str(e)}")
            return {"type": "text", "text": "[Lỗi xử lý hình ảnh]"}

    @classmethod
    async def format_message_content(
        cls, text: str, attachments: Dict[str, Any], session_id: str = ""
    ) -> Union[str, List[Dict[str, Any]]]:
        """
        Main entry point for building multimodal content blocks.
        Attachments: {"image": base64_str, "audio": base64_str}

        Audio is always converted via STT before being passed to the LLM.
        This is the community-standard approach: it is model-agnostic and avoids
        the input_audio format incompatibility between OpenAI, Gemini, and local models.
        """
        caps = get_capabilities()
        blocks = []

        if text:
            blocks.append({"type": "text", "text": text})

        # ── Vision: image_url data URI ────────────────────────────────
        if attachments.get("image"):
            if caps.get("vision"):
                blocks.append(cls.process_image(attachments["image"]))
            else:
                logger.warning("VISION: Skip — capability disabled for current model.")
                blocks.append({"type": "text", "text": "[Model hiện tại không hỗ trợ hình ảnh]"})

        # ── Audio: STT-first pipeline ─────────────────────────────────
        # Convert audio → text via Whisper/STT before passing to LLM.
        # Benefits: works with ALL LLM backends, transcription is auditable,
        # avoids input_audio format fragmentation (OpenAI Realtime vs Gemini Live vs local).
        if attachments.get("audio"):
            if caps.get("stt"):
                logger.info("AUDIO: Converting speech to text via STT pipeline...")
                transcription = await cls.speech_to_text(attachments["audio"], session_id=session_id)
                if transcription and not transcription.startswith("[Lỗi"):
                    logger.info(f"AUDIO: STT succeeded — transcription length={len(transcription)}")
                    blocks.append({"type": "text", "text": f"[Giọng nói của người dùng]: {transcription}"})
                else:
                    logger.warning(f"AUDIO: STT failed or returned error: {transcription}")
                    blocks.append({"type": "text", "text": "[Không thể chuyển đổi giọng nói. Vui lòng thử lại.]"})
            else:
                logger.warning("AUDIO: Skip — STT capability disabled.")
                blocks.append({"type": "text", "text": "[Tính năng nhận dạng giọng nói hiện không khả dụng]"})

        # ── Result formatting ─────────────────────────────────────────
        if not blocks:
            return text or ""
        if len(blocks) == 1 and blocks[0]["type"] == "text":
            return blocks[0]["text"]

        return blocks

    @staticmethod
    async def speech_to_text(audio_base64: str, session_id: str = "") -> str:
        """
        Wrapper for audio pipeline STT. Delegates to audio_pipeline.process_audio.

        Audio pipeline (app.multimodal.audio_pipeline):
          1. Decode base64
          2. Convert via ffmpeg pipe (webm → 16kHz mono PCM)
          3. Parse to numpy array
          4. Run faster-whisper STT

        Returns transcribed Vietnamese text or error message.
        """
        return await process_audio(audio_base64, session_id=session_id)
