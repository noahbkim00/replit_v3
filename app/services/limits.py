import asyncio
import logging
from typing import Any

from app.errors import ClientRequestError
from app.repositories.limits import LimitRepository, UserLimits
from app.repositories.quota import QuotaLimitExceeded, QuotaRepository, UsageReservation
from app.repositories.usage import TokenUsage
from app.repositories.users import User

logger = logging.getLogger(__name__)


class LimitService:
    def __init__(
        self,
        limit_repository: LimitRepository,
        quota_repository: QuotaRepository,
    ) -> None:
        self._limit_repository = limit_repository
        self._quota_repository = quota_repository

    async def reserve_chat_request(
        self, user: User, model: str, request_body: dict[str, Any]
    ) -> UsageReservation:
        estimated_tokens = self._estimated_tokens(request_body)
        try:
            return await asyncio.to_thread(
                self._quota_repository.reserve_chat_request,
                user.id,
                model,
                estimated_tokens,
            )
        except QuotaLimitExceeded as exc:
            if exc.limit_type == "requests_per_minute":
                logger.warning(
                    "limit.rejected",
                    extra={
                        "user_id": user.id,
                        "limit_type": exc.limit_type,
                        "recent_requests": exc.current,
                        "limit": exc.limit,
                    },
                )
            else:
                logger.warning(
                    "limit.rejected",
                    extra={
                        "user_id": user.id,
                        "limit_type": exc.limit_type,
                        "current_tokens": exc.current,
                        "estimated_tokens": exc.estimated_tokens,
                        "limit": exc.limit,
                    },
                )
            raise ClientRequestError(
                str(exc),
                status_code=429,
                error_type="rate_limit_exceeded",
            ) from exc

    async def finalize_success(
        self,
        reservation: UsageReservation,
        usage: TokenUsage,
        latency_ms: float,
    ) -> None:
        await asyncio.to_thread(
            self._quota_repository.finalize_success,
            reservation,
            usage,
            latency_ms,
        )

    async def finalize_failure(
        self,
        reservation: UsageReservation,
        latency_ms: float,
        usage: TokenUsage | None = None,
    ) -> None:
        await asyncio.to_thread(
            self._quota_repository.finalize_failure,
            reservation,
            latency_ms,
            usage,
        )

    def get_user_limits(self, user_id: str) -> dict[str, int | None | str]:
        return self._limits_response(self._limit_repository.get_user_limits(user_id))

    def update_user_limits(
        self,
        user_id: str,
        requests_per_minute: int | None,
        daily_tokens: int | None,
        total_tokens: int | None,
    ) -> dict[str, int | None | str]:
        for limit_name, value in {
            "requests_per_minute": requests_per_minute,
            "daily_tokens": daily_tokens,
            "total_tokens": total_tokens,
        }.items():
            if value is not None and value < 0:
                raise ClientRequestError(f"{limit_name} must be greater than or equal to 0")

        return self._limits_response(
            self._limit_repository.update_user_limits(
                user_id=user_id,
                requests_per_minute=requests_per_minute,
                daily_tokens=daily_tokens,
                total_tokens=total_tokens,
            )
        )

    def _estimated_tokens(self, request_body: dict[str, Any]) -> int:
        max_tokens = request_body.get("max_tokens")
        if isinstance(max_tokens, bool):
            return 0
        if isinstance(max_tokens, int):
            return max(max_tokens, 0)
        return 0

    def _limits_response(self, limits: UserLimits) -> dict[str, int | None | str]:
        return {
            "user_id": limits.user_id,
            "requests_per_minute": limits.requests_per_minute,
            "daily_tokens": limits.daily_tokens,
            "total_tokens": limits.total_tokens,
        }
