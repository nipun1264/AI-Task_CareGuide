from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    database_url: str = "sqlite:///./document_intelligence.db"
    redis_url: str = "redis://localhost:6379/0"
    storage_path: Path = Path("./storage/uploads")
    openai_api_key: str | None = None
    openai_model: str = "gpt-4o-mini"
    max_upload_mb: int = 25


settings = Settings()
settings.storage_path.mkdir(parents=True, exist_ok=True)
