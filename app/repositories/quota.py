from dataclasses import dataclass
from pathlib import Path

from app.db import connect_database
from app.repositories.usage import TokenUsage


@dataclass(frozen=True)
class UsageReservation:
    event_id: int
    user_id: str
    model: str
    estimated_tokens: int


class QuotaLimitExceeded(Exception):
    def __init__(
        self,
        message: str,
        limit_type: str,
        current: int,
        estimated_tokens: int,
        limit: int,
    ) -> None:
        super().__init__(message)
        self.limit_type = limit_type
        self.current = current
        self.estimated_tokens = estimated_tokens
        self.limit = limit


class QuotaRepository:
    def __init__(self, database_path: Path) -> None:
        self._database_path = database_path

    def reserve_chat_request(
        self,
        user_id: str,
        model: str,
        estimated_tokens: int,
    ) -> UsageReservation:
        estimated_tokens = max(estimated_tokens, 0)
        with connect_database(self._database_path) as connection:
            connection.execute("BEGIN IMMEDIATE")
            limits = connection.execute(
                """
                SELECT requests_per_minute, daily_tokens, total_tokens
                FROM user_limits
                WHERE user_id = ?
                """,
                (user_id,),
            ).fetchone()

            requests_per_minute = limits[0] if limits is not None else None
            daily_tokens = limits[1] if limits is not None else None
            total_tokens = limits[2] if limits is not None else None

            if requests_per_minute is not None:
                recent_requests = int(
                    connection.execute(
                        """
                        SELECT COUNT(*)
                        FROM usage_events
                        WHERE user_id = ?
                          AND status IN ('reserved', 'success')
                          AND timestamp >= datetime('now', '-60 seconds')
                        """,
                        (user_id,),
                    ).fetchone()[0]
                )
                if recent_requests >= requests_per_minute:
                    raise QuotaLimitExceeded(
                        "Request rate limit exceeded",
                        limit_type="requests_per_minute",
                        current=recent_requests,
                        estimated_tokens=estimated_tokens,
                        limit=requests_per_minute,
                    )

            if daily_tokens is not None:
                current_daily_tokens = self._sum_reserved_and_successful_tokens_today(
                    connection, user_id
                )
                if current_daily_tokens + estimated_tokens > daily_tokens:
                    raise QuotaLimitExceeded(
                        "Token limit exceeded for daily_tokens",
                        limit_type="daily_tokens",
                        current=current_daily_tokens,
                        estimated_tokens=estimated_tokens,
                        limit=daily_tokens,
                    )

            if total_tokens is not None:
                current_total_tokens = self._sum_reserved_and_successful_tokens(connection, user_id)
                if current_total_tokens + estimated_tokens > total_tokens:
                    raise QuotaLimitExceeded(
                        "Token limit exceeded for total_tokens",
                        limit_type="total_tokens",
                        current=current_total_tokens,
                        estimated_tokens=estimated_tokens,
                        limit=total_tokens,
                    )

            cursor = connection.execute(
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
                VALUES (?, ?, 0, 0, ?, 0, 'reserved')
                """,
                (user_id, model, estimated_tokens),
            )

        return UsageReservation(
            event_id=int(cursor.lastrowid),
            user_id=user_id,
            model=model,
            estimated_tokens=estimated_tokens,
        )

    def finalize_success(
        self,
        reservation: UsageReservation,
        usage: TokenUsage,
        latency_ms: float,
    ) -> None:
        with connect_database(self._database_path) as connection:
            connection.execute(
                """
                UPDATE usage_events
                SET prompt_tokens = ?,
                    completion_tokens = ?,
                    total_tokens = ?,
                    latency_ms = ?,
                    status = 'success'
                WHERE id = ?
                """,
                (
                    usage.prompt_tokens,
                    usage.completion_tokens,
                    usage.total_tokens,
                    latency_ms,
                    reservation.event_id,
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
                    reservation.user_id,
                    reservation.model,
                    usage.prompt_tokens,
                    usage.completion_tokens,
                    usage.total_tokens,
                ),
            )

    def finalize_failure(
        self,
        reservation: UsageReservation,
        latency_ms: float,
        usage: TokenUsage | None = None,
    ) -> None:
        usage = usage or TokenUsage(prompt_tokens=0, completion_tokens=0, total_tokens=0)
        with connect_database(self._database_path) as connection:
            connection.execute(
                """
                UPDATE usage_events
                SET prompt_tokens = ?,
                    completion_tokens = ?,
                    total_tokens = ?,
                    latency_ms = ?,
                    status = 'failed'
                WHERE id = ?
                """,
                (
                    usage.prompt_tokens,
                    usage.completion_tokens,
                    usage.total_tokens,
                    latency_ms,
                    reservation.event_id,
                ),
            )

    def _sum_reserved_and_successful_tokens_today(self, connection, user_id: str) -> int:
        row = connection.execute(
            """
            SELECT COALESCE(SUM(total_tokens), 0)
            FROM usage_events
            WHERE user_id = ?
              AND status IN ('reserved', 'success')
              AND date(timestamp) = date('now')
            """,
            (user_id,),
        ).fetchone()
        return int(row[0])

    def _sum_reserved_and_successful_tokens(self, connection, user_id: str) -> int:
        row = connection.execute(
            """
            SELECT COALESCE(SUM(total_tokens), 0)
            FROM usage_events
            WHERE user_id = ?
              AND status IN ('reserved', 'success')
            """,
            (user_id,),
        ).fetchone()
        return int(row[0])
