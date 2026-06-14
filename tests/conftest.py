import asyncio
import json
import sqlite3
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.clients.ollama import OllamaClient
from app.config import Settings
from app.db import initialize_database
from app.main import create_app
from scripts.seed_dev_data import seed_dev_data


@pytest.fixture
def temp_settings(tmp_path: Path) -> Callable[..., Settings]:
    def build_settings(**overrides: Any) -> Settings:
        return Settings(database_path=tmp_path / "proxy.sqlite3", **overrides)

    return build_settings


@pytest.fixture
def seeded_app(temp_settings: Callable[..., Settings]) -> Callable[..., tuple[FastAPI, Path]]:
    def build_app(**settings_overrides: Any) -> tuple[FastAPI, Path]:
        settings = temp_settings(**settings_overrides)
        initialize_database(settings.database_path)
        seed_dev_data(settings.database_path)
        return create_app(settings), settings.database_path

    return build_app


@pytest.fixture
def client_for() -> Callable[[FastAPI], TestClient]:
    def build_client(app: FastAPI) -> TestClient:
        return TestClient(app)

    return build_client


@pytest.fixture
def user_headers() -> Callable[[str], dict[str, str]]:
    def build_headers(token: str = "dev-token-user-a") -> dict[str, str]:
        return {"Authorization": f"Bearer {token}"}

    return build_headers


@pytest.fixture
def chat_payload() -> Callable[..., dict[str, Any]]:
    def build_payload(
        model: str = "llama3.2:1b",
        content: str = "hello",
        max_tokens: int = 8,
        stream: bool = False,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": model,
            "messages": [{"role": "user", "content": content}],
            "max_tokens": max_tokens,
        }
        if stream:
            payload["stream"] = True
        return payload

    return build_payload


@pytest.fixture
def usage_rows() -> Callable[..., list[tuple[Any, ...]]]:
    def read_rows(database_path: Path, status: str | None = None) -> list[tuple[Any, ...]]:
        query = """
            SELECT user_id, model, prompt_tokens, completion_tokens, total_tokens, status
            FROM usage_events
        """
        params: tuple[Any, ...] = ()
        if status is not None:
            query += " WHERE status = ?"
            params = (status,)
        query += " ORDER BY id"

        with sqlite3.connect(database_path) as connection:
            return connection.execute(query, params).fetchall()

    return read_rows


@pytest.fixture
def usage_totals() -> Callable[[Path], list[tuple[Any, ...]]]:
    def read_totals(database_path: Path) -> list[tuple[Any, ...]]:
        with sqlite3.connect(database_path) as connection:
            return connection.execute(
                """
                SELECT user_id, model, prompt_tokens, completion_tokens, total_tokens, request_count
                FROM usage_totals
                ORDER BY user_id, model
                """
            ).fetchall()

    return read_totals


@pytest.fixture
def sse_chunk() -> Callable[[dict[str, Any]], bytes]:
    def encode_chunk(payload: dict[str, Any]) -> bytes:
        return f"data: {json.dumps(payload)}\n\n".encode()

    return encode_chunk


class StubOllama:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []
        self.stream_calls: list[dict[str, Any]] = []
        self.closed_count = 0
        self.delay_seconds = 0.0
        self.model_response: dict[str, Any] = {
            "object": "list",
            "data": [
                {"id": "llama3.2:1b", "object": "model", "owned_by": "ollama"},
                {"id": "moondream", "object": "model", "owned_by": "ollama"},
            ],
        }
        self.chat_response: dict[str, Any] = {
            "id": "chatcmpl-test",
            "object": "chat.completion",
            "model": "llama3.2:1b",
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": "ok"},
                    "finish_reason": "stop",
                }
            ],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
        }
        self.stream_chunks: list[bytes] = [b"data: [DONE]\n\n"]
        self.chat_error: Exception | None = None
        self.stream_error: Exception | None = None
        self.list_models_error: Exception | None = None


@pytest.fixture
def stub_ollama(monkeypatch: pytest.MonkeyPatch) -> StubOllama:
    stub = StubOllama()

    async def list_models(_self: OllamaClient) -> dict[str, Any]:
        if stub.delay_seconds:
            await asyncio.sleep(stub.delay_seconds)
        if stub.list_models_error is not None:
            raise stub.list_models_error
        return stub.model_response

    async def create_chat_completion(
        _self: OllamaClient, payload: dict[str, Any]
    ) -> dict[str, Any]:
        stub.calls.append(payload)
        if stub.delay_seconds:
            await asyncio.sleep(stub.delay_seconds)
        if stub.chat_error is not None:
            raise stub.chat_error
        return stub.chat_response

    async def stream_chat_completion(_self: OllamaClient, payload: dict[str, Any]):
        stub.stream_calls.append(payload)
        if stub.delay_seconds:
            await asyncio.sleep(stub.delay_seconds)
        for chunk in stub.stream_chunks:
            yield chunk
        if stub.stream_error is not None:
            raise stub.stream_error

    async def aclose(_self: OllamaClient) -> None:
        stub.closed_count += 1

    monkeypatch.setattr(OllamaClient, "list_models", list_models)
    monkeypatch.setattr(OllamaClient, "create_chat_completion", create_chat_completion)
    monkeypatch.setattr(OllamaClient, "stream_chat_completion", stream_chat_completion)
    monkeypatch.setattr(OllamaClient, "aclose", aclose, raising=False)

    return stub
