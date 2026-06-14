from typing import Any

from app.repositories.users import User


class LimitService:
    def check_chat_request(
        self, user: User, model: str, request_body: dict[str, Any]
    ) -> None:
        _ = (user, model, request_body)
