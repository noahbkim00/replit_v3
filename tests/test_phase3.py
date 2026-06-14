import json
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


def seeded_app(tmp_path, **settings_overrides):
    settings = Settings(
        database_path=tmp_path / "proxy.sqlite3",
        **settings_overrides,
    )
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


def sse_chunk(payload: dict[str, Any]) -> bytes:
    return f"data: {json.dumps(payload)}\n\n".encode()


def test_streaming_chat_forwards_incremental_chunks_and_records_final_usage(
    tmp_path, monkeypatch, caplog
):
    app, database_path = seeded_app(tmp_path)
    forwarded_payloads: list[dict[str, Any]] = []

    async def fake_stream_chat_completion(self, payload):
        forwarded_payloads.append(payload)
        yield sse_chunk(
            {
                "id": "chatcmpl-test",
                "object": "chat.completion.chunk",
                "model": "llama3.2:1b",
                "choices": [{"index": 0, "delta": {"content": "he"}}],
            }
        )
        yield sse_chunk(
            {
                "id": "chatcmpl-test",
                "object": "chat.completion.chunk",
                "model": "llama3.2:1b",
                "choices": [{"index": 0, "delta": {"content": "llo"}}],
            }
        )
        yield sse_chunk(
            {
                "id": "chatcmpl-test",
                "object": "chat.completion.chunk",
                "model": "llama3.2:1b",
                "choices": [],
                "usage": {
                    "prompt_tokens": 7,
                    "completion_tokens": 2,
                    "total_tokens": 9,
                },
            }
        )
        yield b"data: [DONE]\n\n"

    monkeypatch.setattr(OllamaClient, "stream_chat_completion", fake_stream_chat_completion)

    request_payload = {
        "model": "llama3.2:1b",
        "messages": [{"role": "user", "content": "Say hello"}],
        "stream": True,
    }
    caplog.set_level(logging.INFO)
    with TestClient(app) as client:
        with client.stream(
            "POST",
            "/v1/chat/completions",
            headers={"Authorization": "Bearer dev-token-user-a"},
            json=request_payload,
        ) as response:
            body = b"".join(response.iter_bytes())

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert b'"content": "he"' in body
    assert b'"content": "llo"' in body
    assert body.endswith(b"data: [DONE]\n\n")
    assert forwarded_payloads == [
        {
            **request_payload,
            "stream_options": {"include_usage": True},
        }
    ]
    assert usage_rows(database_path) == [("user_a", "llama3.2:1b", 7, 2, 9, "success")]
    assert usage_totals(database_path) == [("user_a", "llama3.2:1b", 7, 2, 9, 1)]
    stream_records = [
        record for record in caplog.records if record.message == "chat.stream_completed"
    ]
    assert len(stream_records) == 1
    stream_record = stream_records[0]
    assert stream_record.user_id == "user_a"
    assert stream_record.model == "llama3.2:1b"
    assert stream_record.stream is True
    assert stream_record.prompt_tokens == 7
    assert stream_record.completion_tokens == 2
    assert stream_record.total_tokens == 9
    assert "Say hello" not in caplog.text
    assert '"content": "he"' not in caplog.text


def test_streaming_chat_merges_existing_stream_options(tmp_path, monkeypatch, caplog):
    app, _database_path = seeded_app(tmp_path)
    forwarded_payloads: list[dict[str, Any]] = []

    async def fake_stream_chat_completion(self, payload):
        forwarded_payloads.append(payload)
        yield b"data: [DONE]\n\n"

    monkeypatch.setattr(OllamaClient, "stream_chat_completion", fake_stream_chat_completion)

    caplog.set_level(logging.WARNING)
    with TestClient(app) as client:
        response = client.post(
            "/chat/completions",
            headers={"Authorization": "Bearer dev-token-user-a"},
            json={
                "model": "llama3.2:1b",
                "messages": [{"role": "user", "content": "hello"}],
                "stream": True,
                "stream_options": {"foo": "bar", "include_usage": False},
            },
        )

    assert response.status_code == 200
    assert forwarded_payloads == [
        {
            "model": "llama3.2:1b",
            "messages": [{"role": "user", "content": "hello"}],
            "stream": True,
            "stream_options": {"foo": "bar", "include_usage": True},
        }
    ]
    no_usage_records = [
        record
        for record in caplog.records
        if record.message == "chat.stream_completed_without_usage"
    ]
    assert len(no_usage_records) == 1
    assert no_usage_records[0].user_id == "user_a"
    assert no_usage_records[0].model == "llama3.2:1b"
    assert "hello" not in caplog.text


def test_interrupted_stream_records_failed_usage_event(tmp_path, monkeypatch, caplog):
    app, database_path = seeded_app(tmp_path)

    async def fake_stream_chat_completion(self, payload):
        yield sse_chunk(
            {
                "id": "chatcmpl-test",
                "object": "chat.completion.chunk",
                "choices": [{"index": 0, "delta": {"content": "partial"}}],
            }
        )
        raise UpstreamServiceError("Ollama stream interrupted")

    monkeypatch.setattr(OllamaClient, "stream_chat_completion", fake_stream_chat_completion)

    caplog.set_level(logging.ERROR)
    with TestClient(app, raise_server_exceptions=False) as client:
        with client.stream(
            "POST",
            "/v1/chat/completions",
            headers={"Authorization": "Bearer dev-token-user-a"},
            json={
                "model": "llama3.2:1b",
                "messages": [{"role": "user", "content": "hello"}],
                "stream": True,
            },
        ) as response:
            list(response.iter_bytes())

    assert usage_rows(database_path) == [("user_a", "llama3.2:1b", 0, 0, 0, "failed")]
    assert usage_totals(database_path) == []
    failed_records = [record for record in caplog.records if record.message == "chat.stream_failed"]
    assert len(failed_records) == 1
    assert failed_records[0].user_id == "user_a"
    assert failed_records[0].model == "llama3.2:1b"
    assert failed_records[0].error_type == "upstream_error"
    assert "partial" not in caplog.text
    assert "hello" not in caplog.text


def test_vision_request_accepts_base64_data_url_and_forwards_to_moondream(
    tmp_path, monkeypatch, caplog
):
    app, database_path = seeded_app(tmp_path)
    forwarded_payloads: list[dict[str, Any]] = []

    async def fake_create_chat_completion(self, payload):
        forwarded_payloads.append(payload)
        return {
            "id": "chatcmpl-vision",
            "object": "chat.completion",
            "model": "moondream",
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": "A small image."},
                    "finish_reason": "stop",
                }
            ],
            "usage": {
                "prompt_tokens": 20,
                "completion_tokens": 4,
                "total_tokens": 24,
            },
        }

    monkeypatch.setattr(OllamaClient, "create_chat_completion", fake_create_chat_completion)

    request_payload = {
        "model": "moondream",
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "What is in this image?"},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": "data:image/png;base64,iVBORw0KGgo=",
                        },
                    },
                ],
            }
        ],
        "max_tokens": 32,
    }
    caplog.set_level(logging.INFO)
    with TestClient(app) as client:
        response = client.post(
            "/v1/chat/completions",
            headers={"Authorization": "Bearer dev-token-user-a"},
            json=request_payload,
        )

    assert response.status_code == 200
    assert forwarded_payloads == [request_payload]
    assert usage_rows(database_path) == [("user_a", "moondream", 20, 4, 24, "success")]
    completion_records = [record for record in caplog.records if record.message == "chat.completed"]
    assert len(completion_records) == 1
    assert completion_records[0].model == "moondream"
    assert "What is in this image?" not in caplog.text
    assert "iVBORw0KGgo=" not in caplog.text


def test_vision_request_rejects_remote_image_urls_without_calling_ollama(tmp_path, monkeypatch):
    app, database_path = seeded_app(tmp_path)
    calls = 0

    async def fake_create_chat_completion(self, payload):
        nonlocal calls
        calls += 1
        return {}

    monkeypatch.setattr(OllamaClient, "create_chat_completion", fake_create_chat_completion)

    with TestClient(app) as client:
        response = client.post(
            "/v1/chat/completions",
            headers={"Authorization": "Bearer dev-token-user-a"},
            json={
                "model": "moondream",
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image_url",
                                "image_url": {"url": "https://picsum.photos/seed/replit/320/240"},
                            }
                        ],
                    }
                ],
            },
        )

    assert response.status_code == 400
    assert response.json() == {
        "error": {
            "message": "Remote image URLs are not supported; send a base64 data URL",
            "type": "invalid_request_error",
        }
    }
    assert calls == 0
    assert usage_rows(database_path) == []


def test_chat_request_body_size_limit_is_enforced_before_ollama(tmp_path, monkeypatch, caplog):
    app, database_path = seeded_app(tmp_path, max_request_body_bytes=120)
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
                "model": "llama3.2:1b",
                "messages": [{"role": "user", "content": "x" * 200}],
            },
        )

    assert response.status_code == 413
    assert response.json() == {
        "error": {
            "message": "Request body exceeds the configured size limit",
            "type": "invalid_request_error",
        }
    }
    assert calls == 0
    assert usage_rows(database_path) == []
    rejection_records = [record for record in caplog.records if record.message == "chat.rejected"]
    assert len(rejection_records) == 1
    assert rejection_records[0].reason == "body_too_large"
    assert rejection_records[0].limit_bytes == 120
    assert "x" * 20 not in caplog.text


def test_invalid_json_returns_clean_client_error(tmp_path, caplog):
    app, _database_path = seeded_app(tmp_path)

    caplog.set_level(logging.WARNING)
    with TestClient(app) as client:
        response = client.post(
            "/v1/chat/completions",
            headers={
                "Authorization": "Bearer dev-token-user-a",
                "Content-Type": "application/json",
            },
            content=b"{not-json",
        )

    assert response.status_code == 400
    assert response.json() == {
        "error": {
            "message": "Request body must be valid JSON",
            "type": "invalid_request_error",
        }
    }
    rejection_records = [record for record in caplog.records if record.message == "chat.rejected"]
    assert len(rejection_records) == 1
    assert rejection_records[0].reason == "invalid_json"
    assert "{not-json" not in caplog.text


def test_non_object_json_returns_clean_client_error_and_logs_rejection(tmp_path, caplog):
    app, _database_path = seeded_app(tmp_path)

    caplog.set_level(logging.WARNING)
    with TestClient(app) as client:
        response = client.post(
            "/v1/chat/completions",
            headers={
                "Authorization": "Bearer dev-token-user-a",
                "Content-Type": "application/json",
            },
            content=b'["not-an-object"]',
        )

    assert response.status_code == 400
    assert response.json() == {
        "error": {
            "message": "Request body must be a JSON object",
            "type": "invalid_request_error",
        }
    }
    rejection_records = [record for record in caplog.records if record.message == "chat.rejected"]
    assert len(rejection_records) == 1
    assert rejection_records[0].reason == "body_not_object"
    assert "not-an-object" not in caplog.text
