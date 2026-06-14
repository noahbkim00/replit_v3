import logging
import sqlite3
from typing import Any

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


def usage_rows(database_path):
    with sqlite3.connect(database_path) as connection:
        return connection.execute(
            """
            SELECT user_id, model, prompt_tokens, completion_tokens, total_tokens, status
            FROM usage_events
            ORDER BY id
            """
        ).fetchall()


def usage_totals(database_path):
    with sqlite3.connect(database_path) as connection:
        return connection.execute(
            """
            SELECT user_id, model, prompt_tokens, completion_tokens, total_tokens, request_count
            FROM usage_totals
            ORDER BY user_id, model
            """
        ).fetchall()


def test_chat_completion_forwards_non_streaming_request_and_records_usage(
    tmp_path, monkeypatch, caplog
):
    app, database_path = seeded_app(tmp_path)
    forwarded_payloads: list[dict[str, Any]] = []

    async def fake_create_chat_completion(self, payload):
        forwarded_payloads.append(payload)
        return {
            "id": "chatcmpl-test",
            "object": "chat.completion",
            "model": "llama3.2:1b",
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": "4"},
                    "finish_reason": "stop",
                }
            ],
            "usage": {
                "prompt_tokens": 12,
                "completion_tokens": 3,
                "total_tokens": 15,
            },
        }

    monkeypatch.setattr(OllamaClient, "create_chat_completion", fake_create_chat_completion)

    request_payload = {
        "model": "llama3.2:1b",
        "messages": [{"role": "user", "content": "What is 2+2?"}],
        "temperature": 0.1,
        "max_tokens": 8,
    }
    caplog.set_level(logging.INFO)
    with TestClient(app) as client:
        response = client.post(
            "/v1/chat/completions",
            headers={"Authorization": "Bearer dev-token-user-a"},
            json=request_payload,
        )

    assert response.status_code == 200
    assert response.json()["choices"][0]["message"]["content"] == "4"
    assert forwarded_payloads == [request_payload]
    assert usage_rows(database_path) == [("user_a", "llama3.2:1b", 12, 3, 15, "success")]
    assert usage_totals(database_path) == [("user_a", "llama3.2:1b", 12, 3, 15, 1)]
    completion_records = [record for record in caplog.records if record.message == "chat.completed"]
    assert len(completion_records) == 1
    completion_record = completion_records[0]
    assert completion_record.user_id == "user_a"
    assert completion_record.model == "llama3.2:1b"
    assert completion_record.stream is False
    assert completion_record.status == "success"
    assert completion_record.prompt_tokens == 12
    assert completion_record.completion_tokens == 3
    assert completion_record.total_tokens == 15
    assert "What is 2+2?" not in caplog.text
    assert "dev-token-user-a" not in caplog.text


def test_chat_completion_compatibility_route_records_totals_per_user_and_model(
    tmp_path, monkeypatch
):
    app, database_path = seeded_app(tmp_path)

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
                "completion_tokens": 2,
                "total_tokens": 6,
            },
        }

    monkeypatch.setattr(OllamaClient, "create_chat_completion", fake_create_chat_completion)

    with TestClient(app) as client:
        first_response = client.post(
            "/chat/completions",
            headers={"Authorization": "Bearer dev-token-user-b"},
            json={"model": "llama3.2", "messages": [{"role": "user", "content": "A"}]},
        )
        second_response = client.post(
            "/chat/completions",
            headers={"Authorization": "Bearer dev-token-user-b"},
            json={"model": "llama3.2", "messages": [{"role": "user", "content": "B"}]},
        )

    assert first_response.status_code == 200
    assert second_response.status_code == 200
    assert usage_totals(database_path) == [("user_b", "llama3.2", 8, 4, 12, 2)]


def test_chat_completion_rejects_disallowed_model_without_billing(tmp_path, monkeypatch, caplog):
    app, database_path = seeded_app(tmp_path)
    calls = 0

    async def fake_create_chat_completion(self, payload):
        nonlocal calls
        calls += 1
        return {}

    monkeypatch.setattr(OllamaClient, "create_chat_completion", fake_create_chat_completion)

    caplog.set_level(logging.WARNING)
    with TestClient(app) as client:
        response = client.post(
            "/v1/chat/completions",
            headers={"Authorization": "Bearer dev-token-user-a"},
            json={
                "model": "not-allowed",
                "messages": [{"role": "user", "content": "hello"}],
            },
        )

    assert response.status_code == 400
    assert response.json() == {
        "error": {
            "message": "Model 'not-allowed' is not allowed",
            "type": "invalid_request_error",
        }
    }
    assert calls == 0
    assert usage_rows(database_path) == []
    failed_records = [record for record in caplog.records if record.message == "chat.failed"]
    assert len(failed_records) == 1
    assert failed_records[0].user_id == "user_a"
    assert failed_records[0].model == "not-allowed"
    assert failed_records[0].stream is False
    assert failed_records[0].error_type == "invalid_request_error"
    assert failed_records[0].status_code == 400
    assert "hello" not in caplog.text


def test_chat_completion_invalid_auth_is_not_billed(tmp_path, monkeypatch, caplog):
    app, database_path = seeded_app(tmp_path)
    calls = 0

    async def fake_create_chat_completion(self, payload):
        nonlocal calls
        calls += 1
        return {}

    monkeypatch.setattr(OllamaClient, "create_chat_completion", fake_create_chat_completion)

    caplog.set_level(logging.WARNING)
    with TestClient(app) as client:
        response = client.post(
            "/v1/chat/completions",
            headers={"Authorization": "Bearer invalid"},
            json={
                "model": "llama3.2:1b",
                "messages": [{"role": "user", "content": "hello"}],
            },
        )

    assert response.status_code == 401
    assert calls == 0
    assert usage_rows(database_path) == []
    auth_failures = [record for record in caplog.records if record.message == "auth.failure"]
    assert len(auth_failures) == 1
    assert auth_failures[0].reason == "invalid_token"
    assert "invalid" not in caplog.text
    assert "hello" not in caplog.text


def test_chat_completion_upstream_failure_is_not_billed(tmp_path, monkeypatch, caplog):
    app, database_path = seeded_app(tmp_path)

    async def fake_create_chat_completion(self, payload):
        raise UpstreamServiceError("Ollama is unavailable")

    monkeypatch.setattr(OllamaClient, "create_chat_completion", fake_create_chat_completion)

    caplog.set_level(logging.ERROR)
    with TestClient(app) as client:
        response = client.post(
            "/v1/chat/completions",
            headers={"Authorization": "Bearer dev-token-user-a"},
            json={
                "model": "llama3.2:1b",
                "messages": [{"role": "user", "content": "hello"}],
            },
        )

    assert response.status_code == 502
    assert usage_rows(database_path) == []
    failed_records = [record for record in caplog.records if record.message == "chat.failed"]
    assert len(failed_records) == 1
    assert failed_records[0].user_id == "user_a"
    assert failed_records[0].model == "llama3.2:1b"
    assert failed_records[0].stream is False
    assert failed_records[0].error_type == "upstream_error"
    assert "hello" not in caplog.text
