import os
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field


class Settings(BaseModel):
    model_config = ConfigDict(frozen=True)

    app_name: str = Field(default="fastapi-ollama-proxy")
    database_path: Path = Field(default=Path("data/proxy.sqlite3"))
    ollama_base_url: str = Field(default="http://localhost:11434/v1")
    max_request_body_bytes: int = Field(default=8 * 1024 * 1024)

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
            max_request_body_bytes=int(
                os.getenv(
                    "MAX_REQUEST_BODY_BYTES",
                    str(cls.model_fields["max_request_body_bytes"].default),
                )
            ),
        )


settings = Settings.from_env()
