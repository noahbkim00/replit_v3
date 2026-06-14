from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    ollama_base_url: str = "http://localhost:11434/v1"
    port: int = 8000
    database_url: str = "sqlite:///./proxy.db"
    admin_token: str = "dev-admin-token"
    max_request_body_bytes: int = 10_485_760


@lru_cache
def get_settings() -> Settings:
    return Settings()
