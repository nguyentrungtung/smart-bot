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

    # LiteLLM
    LITELLM_API_BASE: str = "http://localhost:4000"
    LITELLM_API_KEY: str = "sk-litellm-proxy"
    LLM_MODEL: str = "lm-studio-model"
    
    # Multimodal: None=auto-detect from model, True=force on, False=force off
    MULTIMODAL_ENABLED: bool | None = None

    # SocketIO CORS Origins
    CORS_ORIGINS: list[str] = ["http://localhost:3000", "http://127.0.0.1:3000", "http://localhost:5173"]
    
    # MCP Security
    MCP_SERVER_URL: str = "http://localhost:8001"
    MCP_INTERNAL_API_KEY: str = "dev-secure-mcp-key-123"

    # Memory Settings (Hybrid)
    MAX_HISTORY_TOKENS: int = 3000  # Strict limit (with buffer) for LM Studio window
    SUMMARY_THRESHOLD: int = 1500   # Trigger summarization earlier to keep context clean

    # Telegram HITL
    TELEGRAM_BOT_TOKEN: str = "" # If empty, HITL will mock approval output
    TELEGRAM_CHAT_ID: str = ""

    # JWT Authentication
    JWT_ALGORITHM: str = "RS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    JWT_REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # JWT Auth Keypair location (absolute path resolver)
    KEYS_DIR: str = os.getenv("KEYS_DIR", "/app/.keys")



    class Config:
        env_file = ".env"
        extra = "ignore" # Required for skipping docker variables not defined here

settings = Settings()
