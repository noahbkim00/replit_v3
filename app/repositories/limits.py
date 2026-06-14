from dataclasses import dataclass
from pathlib import Path

from app.db import connect_database


@dataclass(frozen=True)
class UserLimits:
    user_id: str
    requests_per_minute: int | None
    daily_tokens: int | None
    total_tokens: int | None


class LimitRepository:
    def __init__(self, database_path: Path) -> None:
        self._database_path = database_path

    def get_user_limits(self, user_id: str) -> UserLimits:
        with connect_database(self._database_path) as connection:
            row = connection.execute(
                """
                SELECT user_id, requests_per_minute, daily_tokens, total_tokens
                FROM user_limits
                WHERE user_id = ?
                """,
                (user_id,),
            ).fetchone()

        if row is None:
            return UserLimits(
                user_id=user_id,
                requests_per_minute=None,
                daily_tokens=None,
                total_tokens=None,
            )

        return UserLimits(
            user_id=row[0],
            requests_per_minute=row[1],
            daily_tokens=row[2],
            total_tokens=row[3],
        )

    def update_user_limits(
        self,
        user_id: str,
        requests_per_minute: int | None,
        daily_tokens: int | None,
        total_tokens: int | None,
    ) -> UserLimits:
        with connect_database(self._database_path) as connection:
            connection.execute(
                """
                INSERT INTO user_limits (
                    user_id,
                    requests_per_minute,
                    daily_tokens,
                    total_tokens
                )
                VALUES (?, ?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    requests_per_minute = excluded.requests_per_minute,
                    daily_tokens = excluded.daily_tokens,
                    total_tokens = excluded.total_tokens,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (user_id, requests_per_minute, daily_tokens, total_tokens),
            )

        return self.get_user_limits(user_id)
