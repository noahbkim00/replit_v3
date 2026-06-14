import logging
from typing import Any

from app.errors import ClientRequestError
from app.repositories.limits import LimitRepository, UserLimits
from app.repositories.usage import UsageRepository
from app.repositories.users import User

logger = logging.getLogger(__name__)


class LimitService:
    def __init__(
        self,
        limit_repository: LimitRepository,
        usage_repository: UsageRepository,
    ) -> None:
        self._limit_repository = limit_repository
        self._usage_repository = usage_repository

    def check_chat_request(self, user: User, model: str, request_body: dict[str, Any]) -> None:
        _ = model
        limits = self._limit_repository.get_user_limits(user.id)
        self._check_request_rate(user.id, limits)
        self._check_token_caps(user.id, limits, self._estimated_tokens(request_body))

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

    def _check_request_rate(self, user_id: str, limits: UserLimits) -> None:
        if limits.requests_per_minute is None:
            return

        recent_requests = self._usage_repository.count_recent_successful_requests(
            user_id=user_id, seconds=60
        )
        if recent_requests >= limits.requests_per_minute:
            logger.warning(
                "limit.rejected",
                extra={
                    "user_id": user_id,
                    "limit_type": "requests_per_minute",
                    "recent_requests": recent_requests,
                    "limit": limits.requests_per_minute,
                },
            )
            raise ClientRequestError(
                "Request rate limit exceeded",
                status_code=429,
                error_type="rate_limit_exceeded",
            )

    def _check_token_caps(self, user_id: str, limits: UserLimits, estimated_tokens: int) -> None:
        if limits.daily_tokens is not None:
            daily_tokens = self._usage_repository.sum_successful_tokens_today(user_id)
            if daily_tokens + estimated_tokens > limits.daily_tokens:
                logger.warning(
                    "limit.rejected",
                    extra={
                        "user_id": user_id,
                        "limit_type": "daily_tokens",
                        "current_tokens": daily_tokens,
                        "estimated_tokens": estimated_tokens,
                        "limit": limits.daily_tokens,
                    },
                )
                raise ClientRequestError(
                    "Token limit exceeded for daily_tokens",
                    status_code=429,
                    error_type="rate_limit_exceeded",
                )

        if limits.total_tokens is not None:
            total_tokens = self._usage_repository.sum_successful_tokens(user_id)
            if total_tokens + estimated_tokens > limits.total_tokens:
                logger.warning(
                    "limit.rejected",
                    extra={
                        "user_id": user_id,
                        "limit_type": "total_tokens",
                        "current_tokens": total_tokens,
                        "estimated_tokens": estimated_tokens,
                        "limit": limits.total_tokens,
                    },
                )
                raise ClientRequestError(
                    "Token limit exceeded for total_tokens",
                    status_code=429,
                    error_type="rate_limit_exceeded",
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
