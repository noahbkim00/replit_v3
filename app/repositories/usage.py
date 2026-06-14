from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.db import connect_database


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
        with connect_database(self._database_path) as connection:
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

    def get_usage_summary(self, user_id: str) -> dict[str, Any]:
        with connect_database(self._database_path) as connection:
            rows = connection.execute(
                """
                SELECT
                    model,
                    prompt_tokens,
                    completion_tokens,
                    total_tokens,
                    request_count
                FROM usage_totals
                WHERE user_id = ?
                ORDER BY model
                """,
                (user_id,),
            ).fetchall()

        models = [
            {
                "model": row[0],
                "prompt_tokens": row[1],
                "completion_tokens": row[2],
                "total_tokens": row[3],
                "request_count": row[4],
            }
            for row in rows
        ]
        return {
            "user_id": user_id,
            "aggregate": {
                "prompt_tokens": sum(model["prompt_tokens"] for model in models),
                "completion_tokens": sum(model["completion_tokens"] for model in models),
                "total_tokens": sum(model["total_tokens"] for model in models),
                "request_count": sum(model["request_count"] for model in models),
            },
            "models": models,
        }

    def list_usage_events(self, user_id: str) -> list[dict[str, Any]]:
        with connect_database(self._database_path) as connection:
            rows = connection.execute(
                """
                SELECT
                    id,
                    user_id,
                    model,
                    prompt_tokens,
                    completion_tokens,
                    total_tokens,
                    latency_ms,
                    status,
                    timestamp
                FROM usage_events
                WHERE user_id = ?
                ORDER BY id
                """,
                (user_id,),
            ).fetchall()

        return [
            {
                "id": row[0],
                "user_id": row[1],
                "model": row[2],
                "prompt_tokens": row[3],
                "completion_tokens": row[4],
                "total_tokens": row[5],
                "latency_ms": row[6],
                "status": row[7],
                "timestamp": row[8],
            }
            for row in rows
        ]

    def count_recent_successful_requests(self, user_id: str, seconds: int) -> int:
        with connect_database(self._database_path) as connection:
            row = connection.execute(
                """
                SELECT COUNT(*)
                FROM usage_events
                WHERE user_id = ?
                  AND status = 'success'
                  AND timestamp >= datetime('now', ?)
                """,
                (user_id, f"-{seconds} seconds"),
            ).fetchone()

        return int(row[0])

    def sum_successful_tokens_today(self, user_id: str) -> int:
        with connect_database(self._database_path) as connection:
            row = connection.execute(
                """
                SELECT COALESCE(SUM(total_tokens), 0)
                FROM usage_events
                WHERE user_id = ?
                  AND status = 'success'
                  AND date(timestamp) = date('now')
                """,
                (user_id,),
            ).fetchone()

        return int(row[0])

    def sum_successful_tokens(self, user_id: str) -> int:
        with connect_database(self._database_path) as connection:
            row = connection.execute(
                """
                SELECT COALESCE(SUM(total_tokens), 0)
                FROM usage_totals
                WHERE user_id = ?
                """,
                (user_id,),
            ).fetchone()

        return int(row[0])
