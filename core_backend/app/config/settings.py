import os
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    # API Configurations
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    
    # Environment (dev/prod)
    ENV: str = "development"

    # Database
    DATABASE_URL: str = "postgresql+psycopg://admin:admin@localhost:5432/smartsales"
    
    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"

    # Embedding Settings
    EMBEDDING_MODEL: str = "lm-studio-embedding"
    EMBEDDING_DIM: int = 768  # Standardized to 768 for both Local and Cloud compatibility

    # LiteLLM
    LITELLM_API_BASE: str = "http://localhost:4000"
    LITELLM_API_KEY: str = "sk-litellm-proxy"
    LLM_MODEL: str = "lm-studio-model"
    
    # Multimodal: None=auto-detect from model, True=force on, False=force off
    MULTIMODAL_ENABLED: bool | None = None
    GUARDS_ENABLED: bool = True

    # SocketIO CORS Origins
    CORS_ORIGINS: list[str] = ["http://localhost:3000", "http://127.0.0.1:3000", "http://localhost:5173", "http://localhost:5174", "http://localhost:8080"]
    
    # MCP Security
    MCP_SERVER_URL: str = "http://localhost:8001"
    MCP_INTERNAL_API_KEY: str = "dev-secure-mcp-key-123"

    # Memory Settings (Hybrid)
    # Context window target: local models with 35k-65k token context.
    # We use ~25% of context for history before summarizing, keeping 75% free for
    # RAG docs, system prompt, and response generation.
    MAX_HISTORY_TOKENS: int = 8000   # Hard trim: ~25% of a 35k context window
    SUMMARY_THRESHOLD: int = 6000    # Trigger summarizer before hard trim kicks in
    MAX_RESPONSE_TOKENS: int = 2048  # Allow richer responses from capable local models
    MAX_HISTORY_MESSAGES: int = 50   # Message count fallback threshold
    LITELLM_RETRY_COUNT: int = 3
    LLM_TIMEOUT_SECONDS: int = 60  # Max wait for any single LLM completion call
    # faster-whisper (SYSTRAN/faster-whisper, Apache-2.0) — runs fully offline, no API key.
    # Sizes: tiny(74MB) | base(142MB) | small(466MB) | medium(1.5GB)
    # Vietnamese WER benchmark: tiny=10.4% | base=8.5% | small=6.3% | medium=5.0%
    # "small" = recommended for Vietnamese (good accuracy, reasonable CPU load).
    WHISPER_MODEL_SIZE: str = "large-v3"

    # Telegram HITL
    TELEGRAM_BOT_TOKEN: str = "" # If empty, HITL will mock approval output
    TELEGRAM_CHAT_ID: str = ""

    # JWT Authentication
    JWT_ALGORITHM: str = "RS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    JWT_REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # JWT Auth Keypair location (absolute path resolver)
    KEYS_DIR: str = os.getenv("KEYS_DIR", "/app/.keys")



    # Debug & Logging
    LOG_LEVEL: str = "INFO"
    DEBUG_LANGCHAIN: bool = False

    class Config:
        env_file = ".env"
        extra = "ignore" # Required for skipping docker variables not defined here

settings = Settings()
