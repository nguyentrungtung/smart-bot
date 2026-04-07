"""
Multimodal Capability Detection

Determines which features (vision, audio) are supported by the current model.
Moved from app.utils to app.multimodal for better organization.
"""
import logging
from app.config.settings import settings

logger = logging.getLogger("multimodal_capabilities")

# Cloud providers supporting vision (image understanding)
VISION_PROVIDERS = ["gemini", "gpt-4o", "gpt-4-vision", "claude-3"]

# Cloud providers supporting native audio (STT/Multimodal Audio)
# Gemini 2.x supports native audio input.
AUDIO_PROVIDERS = ["gemini"]

# Local models (usually no multimodal support in simple setups)
LOCAL_PROVIDERS = ["lm-studio", "ollama", "local", "openai/local"]

def is_local_model(model_name: str) -> bool:
    lower = model_name.lower()
    return any(lower.startswith(p) for p in LOCAL_PROVIDERS)

def detect_capabilities(model_name: str, env_override: bool | None = None) -> dict:
    lower = model_name.lower()
    model_type = "local" if is_local_model(lower) else "cloud"

    if env_override is False:
        return {"vision": False, "stt": False, "model_type": model_type}
    if env_override is True:
        return {"vision": True, "stt": True, "model_type": model_type}

    # Use substring match (not startswith) to handle prefixed model names
    # e.g. "openai/gemini-2.0-flash", "google/gemini-pro" — common LiteLLM proxy formats
    has_vision = any(p in lower for p in VISION_PROVIDERS)
    # STT is server-side via faster-whisper — available regardless of LLM model.
    # We expose this as "stt" (not "audio") to distinguish from native LLM audio input.
    has_stt = True

    logger.info(f"MULTIMODAL CAPABILITIES: model={model_name}, vision={has_vision}, stt={has_stt}")
    return {"vision": has_vision, "stt": has_stt, "model_type": model_type}

def get_capabilities() -> dict:
    env_override = getattr(settings, "MULTIMODAL_ENABLED", None)
    model_name = settings.LLM_MODEL
    return detect_capabilities(model_name, env_override)
