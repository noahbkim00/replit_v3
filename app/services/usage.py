from typing import Any

from app.repositories.usage import UsageRepository


class UsageService:
    def __init__(self, usage_repository: UsageRepository) -> None:
        self._usage_repository = usage_repository

    def get_usage_summary(self, user_id: str) -> dict[str, Any]:
        return self._usage_repository.get_usage_summary(user_id)

    def list_usage_events(self, user_id: str) -> dict[str, Any]:
        return {
            "user_id": user_id,
            "events": self._usage_repository.list_usage_events(user_id),
        }
