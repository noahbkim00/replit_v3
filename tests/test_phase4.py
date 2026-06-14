import sqlite3
from typing import Any

from fastapi.testclient import TestClient

from app.clients.ollama import OllamaClient
from app.config import Settings
from app.db import initialize_database
from app.main import create_app
from scripts.seed_dev_data import seed_dev_data


def seeded_app(tmp_path):
    settings = Settings(database_path=tmp_path / "proxy.sqlite3")
    initialize_database(settings.database_path)
    seed_dev_data(settings.database_path)
    return create_app(settings), settings.database_path


def usage_rows(database_path):
    with sqlite3.connect(database_path) as connection:
        return connection.execute(
            """
            SELECT user_id, model, prompt_tokens, completion_tokens, total_tokens, status
            FROM usage_events
            ORDER BY id
            """
        ).fetchall()


def user_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def chat_payload(max_tokens: int = 8) -> dict[str, Any]:
    return {
        "model": "llama3.2:1b",
        "messages": [{"role": "user", "content": "hello"}],
        "max_tokens": max_tokens,
    }


def test_user_usage_endpoints_only_return_authenticated_users_usage(
    tmp_path, monkeypatch
):
    app, _database_path = seeded_app(tmp_path)

    async def fake_create_chat_completion(self, payload):
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

    monkeypatch.setattr(OllamaClient, "create_chat_completion", fake_create_chat_completion)

    with TestClient(app) as client:
        assert client.post(
            "/v1/chat/completions",
            headers=user_headers("dev-token-user-a"),
            json=chat_payload(),
        ).status_code == 200
        assert client.post(
            "/v1/chat/completions",
            headers=user_headers("dev-token-user-b"),
            json=chat_payload(),
        ).status_code == 200

        user_a_usage = client.get("/usage", headers=user_headers("dev-token-user-a"))
        user_a_events = client.get(
            "/usage/events", headers=user_headers("dev-token-user-a")
        )
        user_b_usage = client.get("/usage", headers=user_headers("dev-token-user-b"))

    assert user_a_usage.status_code == 200
    assert user_a_usage.json() == {
        "user_id": "user_a",
        "aggregate": {
            "prompt_tokens": 3,
            "completion_tokens": 2,
            "total_tokens": 5,
            "request_count": 1,
        },
        "models": [
            {
                "model": "llama3.2:1b",
                "prompt_tokens": 3,
                "completion_tokens": 2,
                "total_tokens": 5,
                "request_count": 1,
            }
        ],
    }
    assert user_a_events.status_code == 200
    assert user_a_events.json()["user_id"] == "user_a"
    assert [
        (event["user_id"], event["model"], event["total_tokens"])
        for event in user_a_events.json()["events"]
    ] == [("user_a", "llama3.2:1b", 5)]
    assert user_b_usage.status_code == 200
    assert user_b_usage.json()["user_id"] == "user_b"
    assert user_b_usage.json()["aggregate"]["total_tokens"] == 5


def test_admin_can_set_get_limits_and_view_a_users_usage(tmp_path, monkeypatch):
    app, _database_path = seeded_app(tmp_path)

    async def fake_create_chat_completion(self, payload):
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
                "prompt_tokens": 4,
                "completion_tokens": 6,
                "total_tokens": 10,
            },
        }

    monkeypatch.setattr(OllamaClient, "create_chat_completion", fake_create_chat_completion)

    with TestClient(app) as client:
        non_admin_response = client.put(
            "/admin/users/user_a/limits",
            headers=user_headers("dev-token-user-a"),
            json={"requests_per_minute": 2},
        )
        set_response = client.put(
            "/admin/users/user_a/limits",
            headers=user_headers("dev-token-admin"),
            json={
                "requests_per_minute": 2,
                "daily_tokens": 100,
                "total_tokens": 250,
            },
        )
        get_response = client.get(
            "/admin/users/user_a/limits", headers=user_headers("dev-token-admin")
        )
        assert client.post(
            "/v1/chat/completions",
            headers=user_headers("dev-token-user-a"),
            json=chat_payload(),
        ).status_code == 200
        usage_response = client.get(
            "/admin/users/user_a/usage", headers=user_headers("dev-token-admin")
        )

    assert non_admin_response.status_code == 403
    assert set_response.status_code == 200
    assert set_response.json() == {
        "user_id": "user_a",
        "requests_per_minute": 2,
        "daily_tokens": 100,
        "total_tokens": 250,
    }
    assert get_response.status_code == 200
    assert get_response.json() == set_response.json()
    assert usage_response.status_code == 200
    assert usage_response.json()["user_id"] == "user_a"
    assert usage_response.json()["aggregate"]["total_tokens"] == 10


def test_requests_per_minute_limit_rejects_before_calling_ollama_and_is_not_billed(
    tmp_path, monkeypatch
):
    app, database_path = seeded_app(tmp_path)
    calls = 0

    async def fake_create_chat_completion(self, payload):
        nonlocal calls
        calls += 1
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
                "prompt_tokens": 1,
                "completion_tokens": 1,
                "total_tokens": 2,
            },
        }

    monkeypatch.setattr(OllamaClient, "create_chat_completion", fake_create_chat_completion)

    with TestClient(app) as client:
        assert client.put(
            "/admin/users/user_a/limits",
            headers=user_headers("dev-token-admin"),
            json={"requests_per_minute": 1},
        ).status_code == 200
        first_response = client.post(
            "/v1/chat/completions",
            headers=user_headers("dev-token-user-a"),
            json=chat_payload(),
        )
        rejected_response = client.post(
            "/v1/chat/completions",
            headers=user_headers("dev-token-user-a"),
            json=chat_payload(),
        )

    assert first_response.status_code == 200
    assert rejected_response.status_code == 429
    assert rejected_response.json()["error"]["type"] == "rate_limit_exceeded"
    assert calls == 1
    assert usage_rows(database_path) == [
        ("user_a", "llama3.2:1b", 1, 1, 2, "success")
    ]


def test_token_limit_uses_max_tokens_projection_before_calling_ollama(
    tmp_path, monkeypatch
):
    app, database_path = seeded_app(tmp_path)
    calls = 0

    async def fake_create_chat_completion(self, payload):
        nonlocal calls
        calls += 1
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
                "prompt_tokens": 4,
                "completion_tokens": 6,
                "total_tokens": 10,
            },
        }

    monkeypatch.setattr(OllamaClient, "create_chat_completion", fake_create_chat_completion)

    with TestClient(app) as client:
        assert client.post(
            "/v1/chat/completions",
            headers=user_headers("dev-token-user-a"),
            json=chat_payload(max_tokens=10),
        ).status_code == 200
        assert client.put(
            "/admin/users/user_a/limits",
            headers=user_headers("dev-token-admin"),
            json={"daily_tokens": 12, "total_tokens": 12},
        ).status_code == 200
        rejected_response = client.post(
            "/v1/chat/completions",
            headers=user_headers("dev-token-user-a"),
            json=chat_payload(max_tokens=3),
        )

    assert rejected_response.status_code == 429
    assert rejected_response.json()["error"]["message"] == (
        "Token limit exceeded for daily_tokens"
    )
    assert calls == 1
    assert usage_rows(database_path) == [
        ("user_a", "llama3.2:1b", 4, 6, 10, "success")
    ]
