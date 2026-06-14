import sqlite3
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class TokenUsage:
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


class UsageRepository:
    def __init__(self, database_path: Path) -> None:
        self._database_path = database_path

    def record_chat_completion(
        self,
        user_id: str,
        model: str,
        usage: TokenUsage,
        latency_ms: float,
        status: str,
    ) -> None:
        with sqlite3.connect(self._database_path) as connection:
            connection.execute(
                """
                INSERT INTO usage_events (
                    user_id,
                    model,
                    prompt_tokens,
                    completion_tokens,
                    total_tokens,
                    latency_ms,
                    status
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    user_id,
                    model,
                    usage.prompt_tokens,
                    usage.completion_tokens,
                    usage.total_tokens,
                    latency_ms,
                    status,
                ),
            )
            connection.execute(
                """
                INSERT INTO usage_totals (
                    user_id,
                    model,
                    prompt_tokens,
                    completion_tokens,
                    total_tokens,
                    request_count
                )
                VALUES (?, ?, ?, ?, ?, 1)
                ON CONFLICT(user_id, model) DO UPDATE SET
                    prompt_tokens = prompt_tokens + excluded.prompt_tokens,
                    completion_tokens = completion_tokens + excluded.completion_tokens,
                    total_tokens = total_tokens + excluded.total_tokens,
                    request_count = request_count + 1,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (
                    user_id,
                    model,
                    usage.prompt_tokens,
                    usage.completion_tokens,
                    usage.total_tokens,
                ),
            )
