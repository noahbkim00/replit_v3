import asyncio
import sqlite3
from typing import Any

import httpx
from fastapi.testclient import TestClient

from app.clients.ollama import OllamaClient
from app.config import Settings
from app.db import initialize_database
from app.errors import UpstreamServiceError
from app.main import create_app
from scripts.seed_dev_data import seed_dev_data


def seeded_app(tmp_path):
    settings = Settings(database_path=tmp_path / "proxy.sqlite3")
    initialize_database(settings.database_path)
    seed_dev_data(settings.database_path)
    return create_app(settings), settings.database_path


def user_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def chat_payload(max_tokens: int = 1) -> dict[str, Any]:
    return {
        "model": "llama3.2:1b",
        "messages": [{"role": "user", "content": "hello"}],
        "max_tokens": max_tokens,
    }


def usage_rows(database_path):
    with sqlite3.connect(database_path) as connection:
        return connection.execute(
            """
            SELECT user_id, model, prompt_tokens, completion_tokens, total_tokens, status
            FROM usage_events
            ORDER BY id
            """
        ).fetchall()


async def _post_concurrently(
    app,
    path: str,
    headers: dict[str, str],
    payload: dict[str, Any],
    count: int,
) -> list[httpx.Response]:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        return await asyncio.gather(
            *(client.post(path, headers=headers, json=payload) for _ in range(count))
        )


def test_concurrent_requests_per_minute_limit_allows_one_upstream_call(
    tmp_path, monkeypatch
):
    app, database_path = seeded_app(tmp_path)
    calls = 0

    async def fake_create_chat_completion(self, payload):
        nonlocal calls
        calls += 1
        await asyncio.sleep(0.05)
        return {
            "id": "chatcmpl-test",
            "object": "chat.completion",
            "model": payload["model"],
            "choices": [{"index": 0, "message": {"role": "assistant", "content": "ok"}}],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
        }

    monkeypatch.setattr(OllamaClient, "create_chat_completion", fake_create_chat_completion)

    with TestClient(app) as client:
        assert (
            client.put(
                "/admin/users/user_a/limits",
                headers=user_headers("dev-token-admin"),
                json={"requests_per_minute": 1},
            ).status_code
            == 200
        )
        responses = asyncio.run(
            _post_concurrently(
                app,
                "/v1/chat/completions",
                user_headers("dev-token-user-a"),
                chat_payload(max_tokens=1),
                count=5,
            )
        )

    assert sorted(response.status_code for response in responses) == [200, 429, 429, 429, 429]
    assert calls == 1
    assert usage_rows(database_path) == [("user_a", "llama3.2:1b", 1, 1, 2, "success")]


def test_concurrent_token_limit_reserves_projected_usage_before_upstream(
    tmp_path, monkeypatch
):
    app, database_path = seeded_app(tmp_path)
    calls = 0

    async def fake_create_chat_completion(self, payload):
        nonlocal calls
        calls += 1
        await asyncio.sleep(0.05)
        return {
            "id": "chatcmpl-test",
            "object": "chat.completion",
            "model": payload["model"],
            "choices": [{"index": 0, "message": {"role": "assistant", "content": "ok"}}],
            "usage": {"prompt_tokens": 0, "completion_tokens": 1, "total_tokens": 1},
        }

    monkeypatch.setattr(OllamaClient, "create_chat_completion", fake_create_chat_completion)

    with TestClient(app) as client:
        assert (
            client.put(
                "/admin/users/user_a/limits",
                headers=user_headers("dev-token-admin"),
                json={"daily_tokens": 1, "total_tokens": 1},
            ).status_code
            == 200
        )
        responses = asyncio.run(
            _post_concurrently(
                app,
                "/v1/chat/completions",
                user_headers("dev-token-user-a"),
                chat_payload(max_tokens=1),
                count=5,
            )
        )

    assert sorted(response.status_code for response in responses) == [200, 429, 429, 429, 429]
    assert calls == 1
    assert usage_rows(database_path) == [("user_a", "llama3.2:1b", 0, 1, 1, "success")]


def test_interrupted_stream_records_failed_usage_event(tmp_path, monkeypatch):
    app, database_path = seeded_app(tmp_path)

    async def fake_stream_chat_completion(self, payload):
        yield b'data: {"choices":[{"delta":{"content":"partial"}}]}\n\n'
        raise UpstreamServiceError("Ollama stream interrupted")

    monkeypatch.setattr(OllamaClient, "stream_chat_completion", fake_stream_chat_completion)

    with TestClient(app, raise_server_exceptions=False) as client:
        with client.stream(
            "POST",
            "/v1/chat/completions",
            headers=user_headers("dev-token-user-a"),
            json={**chat_payload(max_tokens=1), "stream": True},
        ) as response:
            list(response.iter_bytes())

    assert usage_rows(database_path) == [("user_a", "llama3.2:1b", 0, 0, 0, "failed")]


def test_app_reuses_shared_ollama_client_and_closes_it_on_shutdown(tmp_path, monkeypatch):
    app, _database_path = seeded_app(tmp_path)
    client_ids: list[int] = []
    closed_client_ids: list[int] = []

    async def fake_create_chat_completion(self, payload):
        client_ids.append(id(self))
        return {
            "id": "chatcmpl-test",
            "object": "chat.completion",
            "model": payload["model"],
            "choices": [{"index": 0, "message": {"role": "assistant", "content": "ok"}}],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
        }

    async def fake_aclose(self):
        closed_client_ids.append(id(self))

    monkeypatch.setattr(OllamaClient, "create_chat_completion", fake_create_chat_completion)
    monkeypatch.setattr(OllamaClient, "aclose", fake_aclose, raising=False)

    with TestClient(app) as client:
        first_response = client.post(
            "/v1/chat/completions",
            headers=user_headers("dev-token-user-a"),
            json=chat_payload(max_tokens=1),
        )
        second_response = client.post(
            "/v1/chat/completions",
            headers=user_headers("dev-token-user-a"),
            json=chat_payload(max_tokens=1),
        )
        shared_client_id = id(app.state.ollama_client)

    assert first_response.status_code == 200
    assert second_response.status_code == 200
    assert client_ids == [shared_client_id, shared_client_id]
    assert closed_client_ids == [shared_client_id]
