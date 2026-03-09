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
    LITELLM_URL: str = "http://localhost:4000"
    LITELLM_KEY: str = "sk-litellm-proxy"
    LLM_MODEL: str = "lm-studio-model"

    # SocketIO CORS Origins
    CORS_ORIGINS: list[str] = ["http://localhost:3000", "http://127.0.0.1:3000"]
    
    # MCP Security
    MCP_INTERNAL_API_KEY: str = "dev-secure-mcp-key-123"

    # Telegram HITL
    TELEGRAM_BOT_TOKEN: str = "" # If empty, HITL will mock approval output
    TELEGRAM_CHAT_ID: str = ""

    # JWT Auth Keypair location (absolute path resolver)
    KEYS_DIR: str = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".keys"))

    class Config:
        env_file = ".env"
        extra = "ignore" # Required for skipping docker variables not defined here

settings = Settings()
