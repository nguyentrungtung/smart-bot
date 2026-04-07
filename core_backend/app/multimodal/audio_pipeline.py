"""
Audio Processing Pipeline — Modular, step-by-step processing.

Pipeline Steps:
  1. DECODE   → base64 audio bytes
  2. CONVERT  → ffmpeg pipe: webm/ogg → 16kHz mono PCM s16le (no temp files)
  3. PARSE    → numpy float32 array for faster-whisper
  4. TRANSCRIBE → STT Vietnamese text

Community standard: Use ffmpeg pipes to avoid filesystem I/O bottlenecks.
faster-whisper accepts numpy arrays directly, enabling memory-only pipeline.

Reference: SYSTRAN/faster-whisper (21.9k⭐) supports 99 languages including Vietnamese.
"""

import asyncio
import base64
import logging
import re
import numpy as np
from typing import Optional

from app.config.settings import settings

logger = logging.getLogger("audio_pipeline")

_SAMPLE_RATE = 16000  # Whisper requirement
_MIN_AUDIO_DURATION_S = 0.3  # Reject clips < 300ms

# faster-whisper model singleton — lazy-loaded on first use
_whisper_model = None
_WHISPER_MODEL_SIZE = getattr(settings, "WHISPER_MODEL_SIZE", "small")


def _get_whisper_model():
    """
    Lazy-load faster-whisper model (downloaded once from HuggingFace cache).
    Called from _transcribe() in thread executor.
    """
    global _whisper_model
    if _whisper_model is None:
        from faster_whisper import WhisperModel

        logger.info(
            f"STT: Loading faster-whisper model '{_WHISPER_MODEL_SIZE}' on CPU "
            f"(first call only, ~10s delay)..."
        )
        _whisper_model = WhisperModel(
            _WHISPER_MODEL_SIZE, device="cpu", compute_type="int8"
        )
        logger.info("STT: faster-whisper model loaded and ready.")
    return _whisper_model


async def _validate_audio_format(audio_bytes: bytes) -> str:
    """
    Validate audio format from magic bytes (first 12 bytes).
    Prevents FFmpeg errors on corrupt/invalid headers.

    Returns: format string (e.g., "webm", "wav", "ogg")
    Raises: ValueError if format unrecognized
    """
    magic = audio_bytes[:12]

    # WebM/Matroska: 0x1A 0x45 0xDF 0xA3
    if magic.startswith(b'\x1a\x45\xdf\xa3'):
        return "webm"

    # WAV: "RIFF" + ... + "WAVE"
    if magic.startswith(b'RIFF') and b'WAVE' in audio_bytes[:44]:
        return "wav"

    # Ogg/Opus: "OggS"
    if magic.startswith(b'OggS'):
        return "ogg"

    # MP3 ID3 Tag
    if magic.startswith(b'ID3'):
        return "mp3"

    # MP3 Sync Frame (0xFF followed by top 3 bits = 111)
    if magic.startswith(b'\xff') and len(magic) > 1 and (magic[1] & 0xE0) == 0xE0:
        return "mp3"

    # AAC ADTS frame sync (0xFF followed by top 4 bits = 1111)
    if magic.startswith(b'\xff') and len(magic) > 1 and (magic[1] & 0xF0) == 0xF0:
        return "aac"

    # Fallback: warn but let ffmpeg attempt to auto-detect
    logger.warning(f"AUDIO: Unknown format. Magic bytes: {magic.hex()}. Falling back to ffmpeg auto-detect.")
    return "unknown"


async def process_audio(audio_b64: str, session_id: str = "") -> str:
    """
    Full audio pipeline: base64 audio → Vietnamese text transcription.

    Args:
        audio_b64: Base64-encoded audio from browser (webm/ogg/mp4)
        session_id: For tracing/logging (e.g., "sess_abc123")

    Returns:
        Transcribed Vietnamese text, or error message on failure
    """
    pfx = f"[{session_id[:8]}] AUDIO" if session_id else "AUDIO"

    # ─ STEP 1: DECODE + FORMAT VALIDATION ────────────────────────────────
    try:
        raw_data = audio_b64.split(",")[-1]  # Strip data: URI prefix
        audio_bytes = base64.b64decode(raw_data)

        # Validate format before expensive FFmpeg call
        fmt = await _validate_audio_format(audio_bytes)
        logger.info(f"{pfx} ├─ [1/4] DECODE: {fmt} format, {len(audio_bytes):,} bytes")

    except Exception as e:
        logger.error(f"{pfx} ├─ [1/4] DECODE FAILED: {e}")
        return "[Lỗi giải mã audio]"

    # ─ STEP 2: CONVERT (ffmpeg pipe) ──────────────────────────────────────
    try:
        pcm_bytes = await _ffmpeg_to_pcm(audio_bytes)
        duration_s = len(pcm_bytes) / (2 * _SAMPLE_RATE)  # 2 bytes/s16le sample
        logger.info(f"{pfx} ├─ [2/4] CONVERT: {duration_s:.2f}s of 16kHz mono PCM")

        if duration_s < _MIN_AUDIO_DURATION_S:
            logger.warning(f"{pfx} ├─ Audio too short ({duration_s:.2f}s). Skipping.")
            return "[Giọng nói quá ngắn]"
    except asyncio.TimeoutError:
        logger.error(f"{pfx} ├─ [2/4] CONVERT TIMEOUT: ffmpeg exceeded 30s")
        return "[Lỗi xử lý audio (quá lâu)]"
    except Exception as e:
        logger.error(f"{pfx} ├─ [2/4] CONVERT FAILED: {str(e)[:100]}")
        return "[Lỗi chuyển đổi định dạng audio]"

    # ─ STEP 3: PARSE (bytes → numpy) ──────────────────────────────────────
    try:
        audio_np = np.frombuffer(pcm_bytes, dtype=np.int16).astype(np.float32) / 32768.0
        logger.info(f"{pfx} ├─ [3/4] PARSE: numpy {audio_np.shape} dtype={audio_np.dtype}")
    except Exception as e:
        logger.error(f"{pfx} ├─ [3/4] PARSE FAILED: {e}")
        return "[Lỗi xử lý audio]"

    # ─ STEP 4: TRANSCRIBE (faster-whisper STT) ────────────────────────────
    try:
        text = await _transcribe(audio_np, session_id=session_id)
        if not text:
            logger.warning(f"{pfx} └─ [4/4] TRANSCRIBE: empty result")
            return "[Không nhận diện được giọng nói]"

        logger.info(f"{pfx} └─ [4/4] TRANSCRIBE ({len(text)} chars): '{text}'")
        return text

    except asyncio.TimeoutError:
        logger.error(f"{pfx} └─ [4/4] TRANSCRIBE TIMEOUT: STT exceeded 30s")
        return "[Lỗi nhận diện giọng nói (quá lâu)]"
    except Exception as e:
        logger.error(f"{pfx} └─ [4/4] TRANSCRIBE FAILED: {str(e)[:100]}")
        return "[Lỗi nhận diện giọng nói]"


async def _ffmpeg_to_pcm(audio_bytes: bytes) -> bytes:
    """
    Convert browser audio (webm/ogg/mp4) to raw 16kHz mono PCM s16le via ffmpeg pipe.

    Key: Uses stdin/stdout pipes — zero temp files, zero disk I/O.
    Input is streamed through ffmpeg, output is streamed back.

    Args:
        audio_bytes: Raw audio data from browser

    Returns:
        Raw 16-bit signed PCM data (s16le format, no WAV header)

    Raises:
        RuntimeError: ffmpeg failed to convert
        asyncio.TimeoutError: conversion exceeded 30s
    """
    proc = await asyncio.create_subprocess_exec(
        "ffmpeg",
        "-hide_banner", "-loglevel", "error",  # Suppress progress spam
        "-i", "pipe:0",                         # Input from stdin
        "-ar", str(_SAMPLE_RATE),               # Resample to 16kHz
        "-ac", "1",                             # Convert to mono
        "-f", "s16le",                          # Output raw signed 16-bit PCM
        "pipe:1",                               # Output to stdout
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    try:
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(input=audio_bytes),
            timeout=60.0,  # Increase from 30s to 60s for slow networks (format conversion can be CPU-bound)
        )
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        raise

    if proc.returncode != 0:
        raise RuntimeError(
            f"ffmpeg error (code {proc.returncode}): {stderr.decode()[:200]}"
        )

    return stdout


async def _transcribe(audio_np: np.ndarray, session_id: str = "") -> str:
    """
    Run faster-whisper STT in thread pool (CPU-bound work must not block event loop).

    Args:
        audio_np: float32 numpy array (values in [-1.0, 1.0])
        session_id: For logging

    Returns:
        Transcribed Vietnamese text (empty string if no speech detected)

    Raises:
        asyncio.TimeoutError: transcription exceeded 30s
    """
    pfx = f"[{session_id[:8]}]" if session_id else "STT"

    def _run():
        """Run in thread pool — do not await."""
        model = _get_whisper_model()
        logger.debug(f"{pfx} faster-whisper transcribe starting...")

        segments, info = model.transcribe(
            audio_np,
            language="vi",  # Vietnamese — skip language detection
            beam_size=5,
            vad_filter=True,
            vad_parameters={
                "min_silence_duration_ms": 300,  # Don't cut short Vietnamese utterances
                "speech_pad_ms": 200,
            },
            initial_prompt="Đây là đoạn hội thoại tiếng Việt.",
            condition_on_previous_text=False,
        )

        transcription = "".join(seg.text for seg in segments).strip()
        confidence = info.language_probability

        logger.info(
            f"{pfx} STT RESULT: language={info.language}, "
            f"confidence={confidence:.2%}, "
            f"text_len={len(transcription)}, "
            f"decision={'ACCEPT' if confidence > 0.5 else 'REJECT'}"
        )

        # Reject low-confidence transcriptions (noise, silence, wrong language)
        if confidence < 0.5:
            logger.warning(
                f"{pfx} STT: Low language confidence ({confidence:.2%}). "
                f"Expected Vietnamese but got weak signal. Rejecting."
            )
            return ""

        return transcription

    loop = asyncio.get_running_loop()
    try:
        text = await asyncio.wait_for(
            loop.run_in_executor(None, _run),
            timeout=30.0,
        )
        return text
    except asyncio.TimeoutError:
        logger.error(f"{pfx} Transcription timed out (30s)")
        raise
