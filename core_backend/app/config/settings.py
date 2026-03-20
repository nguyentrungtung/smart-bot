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
    EMBEDDING_DIM: int = 768  # Standardized to 768 for both Local and Cloud compatibility

    # LiteLLM
    LITELLM_API_BASE: str = "http://localhost:4000"
    LITELLM_API_KEY: str = "sk-litellm-proxy"
    LLM_MODEL: str = "lm-studio-model"
    
    # Multimodal: None=auto-detect from model, True=force on, False=force off
    MULTIMODAL_ENABLED: bool | None = None
    GUARDS_ENABLED: bool = True

    # SocketIO CORS Origins
    CORS_ORIGINS: list[str] = ["http://localhost:3000", "http://127.0.0.1:3000", "http://localhost:5173", "http://localhost:8080"]
    
    # MCP Security
    MCP_SERVER_URL: str = "http://localhost:8001"
    MCP_INTERNAL_API_KEY: str = "dev-secure-mcp-key-123"

    # Memory Settings (Hybrid)
    # MAX_HISTORY_TOKENS: int = 1000  # Lowered further for stability
    # SUMMARY_THRESHOLD: int = 600    # Summarize even earlier
    MAX_HISTORY_TOKENS: int = 500  # Lowered further for testing
    SUMMARY_THRESHOLD: int = 300    # Summarize even earlier
    MAX_RESPONSE_TOKENS: int = 500  # Prevent AI from generating too long a response
    MAX_HISTORY_MESSAGES: int = 10 # Threshold for summarization based on message count
    LITELLM_RETRY_COUNT: int = 3

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
