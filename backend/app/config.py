from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    app_name: str = "Knowledge Base AI Assistant"

    # Database
    database_url: str = "postgresql+asyncpg://kb_user:kb_password@localhost:5432/knowledge_base"

    # OpenAI
    openai_api_key: str = ""
    openai_embedding_model: str = "text-embedding-ada-002"
    openai_chat_model: str = "gpt-4"

    # JWT
    jwt_secret_key: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 30
    jwt_refresh_token_expire_days: int = 7

    # Upload
    upload_dir: str = "./uploads"
    max_upload_size_mb: int = 50

    # Chunking
    chunk_size: int = 512
    chunk_overlap: int = 64

    # RAG
    similarity_threshold: float = 0.75
    max_retrieval_count: int = 5

    # Conversation Memory
    conversation_history_limit: int = 10
    history_token_budget: int = 2048

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


@lru_cache()
def get_settings() -> Settings:
    return Settings()
