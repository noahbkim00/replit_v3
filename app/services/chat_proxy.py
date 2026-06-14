from time import perf_counter
from typing import Any

from app.clients.ollama import OllamaClient
from app.errors import ClientRequestError
from app.repositories.models import ModelRepository
from app.repositories.usage import TokenUsage, UsageRepository
from app.repositories.users import User
from app.services.limits import LimitService


class ChatProxyService:
    def __init__(
        self,
        model_repository: ModelRepository,
        ollama_client: OllamaClient,
        usage_repository: UsageRepository,
        limit_service: LimitService,
    ) -> None:
        self._model_repository = model_repository
        self._ollama_client = ollama_client
        self._usage_repository = usage_repository
        self._limit_service = limit_service

    async def create_chat_completion(
        self, user: User, request_body: dict[str, Any]
    ) -> dict[str, Any]:
        model = self._validate_request(request_body)
        self._limit_service.check_chat_request(user, model, request_body)

        started_at = perf_counter()
        response_body = await self._ollama_client.create_chat_completion(request_body)
        latency_ms = (perf_counter() - started_at) * 1000

        self._usage_repository.record_chat_completion(
            user_id=user.id,
            model=model,
            usage=self._extract_usage(response_body),
            latency_ms=latency_ms,
            status="success",
        )
        return response_body

    def _validate_request(self, request_body: dict[str, Any]) -> str:
        model = request_body.get("model")
        if not isinstance(model, str) or not model:
            raise ClientRequestError("Request body must include a model")

        if request_body.get("stream") is True:
            raise ClientRequestError("stream=true is not supported yet")

        allowed_model_ids = self._model_repository.list_allowed_model_ids()
        if model not in allowed_model_ids:
            raise ClientRequestError(f"Model '{model}' is not allowed")

        return model

    def _extract_usage(self, response_body: dict[str, Any]) -> TokenUsage:
        usage = response_body.get("usage")
        if not isinstance(usage, dict):
            return TokenUsage(prompt_tokens=0, completion_tokens=0, total_tokens=0)

        prompt_tokens = self._usage_int(usage.get("prompt_tokens"))
        completion_tokens = self._usage_int(usage.get("completion_tokens"))
        total_tokens = self._usage_int(usage.get("total_tokens"))
        if total_tokens == 0:
            total_tokens = prompt_tokens + completion_tokens

        return TokenUsage(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
        )

    def _usage_int(self, value: Any) -> int:
        if isinstance(value, bool):
            return 0
        if isinstance(value, int):
            return max(value, 0)
        return 0
