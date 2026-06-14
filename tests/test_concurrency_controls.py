import asyncio
from typing import Any

from app.config import Settings
from app.repositories.quota import UsageReservation
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
    limit_service = _FakeLimitService()
    ollama_client = _SlowOllamaClient()
    service = ChatProxyService(
        model_repository=model_repository,
        ollama_client=ollama_client,
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
    assert len(limit_service.successes) == 5


class _FakeModelRepository:
    def list_allowed_model_ids(self) -> set[str]:
        return {"llama3.2:1b"}


class _FakeLimitService:
    def __init__(self) -> None:
        self.next_event_id = 1
        self.successes: list[dict[str, Any]] = []
        self.failures: list[dict[str, Any]] = []

    async def reserve_chat_request(
        self, user: User, model: str, request_body: dict[str, Any]
    ) -> UsageReservation:
        _ = user, model, request_body
        event_id = self.next_event_id
        self.next_event_id += 1
        return UsageReservation(
            event_id=event_id,
            user_id=user.id,
            model=model,
            estimated_tokens=0,
        )

    async def finalize_success(
        self,
        reservation: UsageReservation,
        usage: TokenUsage,
        latency_ms: float,
    ) -> None:
        self.successes.append(
            {
                "reservation": reservation,
                "usage": usage,
                "latency_ms": latency_ms,
            }
        )

    async def finalize_failure(
        self,
        reservation: UsageReservation,
        latency_ms: float,
        usage: TokenUsage | None = None,
    ) -> None:
        self.failures.append(
            {
                "reservation": reservation,
                "usage": usage,
                "latency_ms": latency_ms,
            }
        )


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
