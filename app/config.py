import os
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field


class Settings(BaseModel):
    model_config = ConfigDict(frozen=True)

    app_name: str = Field(default="fastapi-ollama-proxy")
    database_path: Path = Field(default=Path("data/proxy.sqlite3"))
    ollama_base_url: str = Field(default="http://localhost:11434/v1")
    ollama_timeout_seconds: float = Field(default=30.0)
    ollama_max_concurrency: int = Field(default=4)
    max_request_body_bytes: int = Field(default=8 * 1024 * 1024)
    log_level: str = Field(default="INFO")

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            app_name=os.getenv("APP_NAME", cls.model_fields["app_name"].default),
            database_path=Path(
                os.getenv("DATABASE_PATH", str(cls.model_fields["database_path"].default))
            ),
            ollama_base_url=os.getenv(
                "OLLAMA_BASE_URL", cls.model_fields["ollama_base_url"].default
            ),
            ollama_timeout_seconds=float(
                os.getenv(
                    "OLLAMA_TIMEOUT_SECONDS",
                    str(cls.model_fields["ollama_timeout_seconds"].default),
                )
            ),
            ollama_max_concurrency=max(
                int(
                    os.getenv(
                        "OLLAMA_MAX_CONCURRENCY",
                        str(cls.model_fields["ollama_max_concurrency"].default),
                    )
                ),
                1,
            ),
            max_request_body_bytes=int(
                os.getenv(
                    "MAX_REQUEST_BODY_BYTES",
                    str(cls.model_fields["max_request_body_bytes"].default),
                )
            ),
            log_level=os.getenv("LOG_LEVEL", cls.model_fields["log_level"].default),
        )


settings = Settings.from_env()
