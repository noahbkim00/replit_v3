import asyncio
from typing import Any

from app.config import Settings
from app.repositories.usage import TokenUsage
from app.repositories.users import User
from app.services import chat_proxy
from app.services.chat_proxy import ChatProxyService


def test_settings_load_ollama_timeout_and_concurrency_from_env(monkeypatch):
    monkeypatch.setenv("OLLAMA_TIMEOUT_SECONDS", "30")
    monkeypatch.setenv("OLLAMA_MAX_CONCURRENCY", "4")

    settings = Settings.from_env()

    assert settings.ollama_timeout_seconds == 30.0
    assert settings.ollama_max_concurrency == 4


def test_chat_proxy_service_limits_concurrent_ollama_calls():
    limiter_cls = getattr(chat_proxy, "OllamaConcurrencyLimiter", None)
    assert limiter_cls is not None

    model_repository = _FakeModelRepository()
    usage_repository = _FakeUsageRepository()
    limit_service = _FakeLimitService()
    ollama_client = _SlowOllamaClient()
    service = ChatProxyService(
        model_repository=model_repository,
        ollama_client=ollama_client,
        usage_repository=usage_repository,
        limit_service=limit_service,
        ollama_concurrency_limiter=limiter_cls(max_concurrency=2),
    )
    user = User(id="user_a", display_name="User A", role="user")
    request_body = {
        "model": "llama3.2:1b",
        "messages": [{"role": "user", "content": "hello"}],
    }

    async def run_requests() -> None:
        await asyncio.gather(
            *(service.create_chat_completion(user, request_body) for _ in range(5))
        )

    asyncio.run(run_requests())

    assert ollama_client.max_active_calls == 2
    assert len(usage_repository.records) == 5


class _FakeModelRepository:
    def list_allowed_model_ids(self) -> set[str]:
        return {"llama3.2:1b"}


class _FakeUsageRepository:
    def __init__(self) -> None:
        self.records: list[dict[str, Any]] = []

    def record_chat_completion(
        self,
        user_id: str,
        model: str,
        usage: TokenUsage,
        latency_ms: float,
        status: str,
    ) -> None:
        self.records.append(
            {
                "user_id": user_id,
                "model": model,
                "usage": usage,
                "latency_ms": latency_ms,
                "status": status,
            }
        )


class _FakeLimitService:
    def check_chat_request(
        self, user: User, model: str, request_body: dict[str, Any]
    ) -> None:
        _ = user, model, request_body


class _SlowOllamaClient:
    def __init__(self) -> None:
        self.active_calls = 0
        self.max_active_calls = 0

    async def create_chat_completion(self, payload: dict[str, Any]) -> dict[str, Any]:
        self.active_calls += 1
        self.max_active_calls = max(self.max_active_calls, self.active_calls)
        try:
            await asyncio.sleep(0.01)
            return {
                "id": "chatcmpl-test",
                "object": "chat.completion",
                "model": payload["model"],
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": "ok"},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {
                    "prompt_tokens": 3,
                    "completion_tokens": 2,
                    "total_tokens": 5,
                },
            }
        finally:
            self.active_calls -= 1
