import asyncio
import logging
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

from fastapi.security import HTTPAuthorizationCredentials
from fastapi.testclient import TestClient

from app.api import deps
from app.clients.ollama import OllamaClient
from app.config import Settings
from app.db import initialize_database
from app.main import create_app
from app.repositories.users import User
from scripts.seed_dev_data import seed_dev_data

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_seed_dev_data_creates_users_tokens_and_model_allowlist(tmp_path):
    database_path = tmp_path / "proxy.sqlite3"

    initialize_database(database_path)
    seed_dev_data(database_path)

    with sqlite3.connect(database_path) as connection:
        users = connection.execute("SELECT id, role FROM users ORDER BY id").fetchall()
        token_count = connection.execute("SELECT COUNT(*) FROM api_tokens").fetchone()
        allowed_models = connection.execute(
            "SELECT model_id FROM model_allowlist ORDER BY model_id"
        ).fetchall()

    assert users == [("admin", "admin"), ("user_a", "user"), ("user_b", "user")]
    assert token_count == (3,)
    assert allowed_models == [("llama3.2",), ("llama3.2:1b",), ("moondream",)]


def test_seed_script_does_not_require_pydantic_for_database_path(tmp_path):
    blocked_imports_path = tmp_path / "blocked_imports"
    blocked_imports_path.mkdir()
    (blocked_imports_path / "pydantic.py").write_text(
        "raise ModuleNotFoundError(\"No module named 'pydantic'\")\n"
    )
    database_path = tmp_path / "proxy.sqlite3"
    env = {
        **os.environ,
        "DATABASE_PATH": str(database_path),
        "PYTHONPATH": str(blocked_imports_path),
    }

    result = subprocess.run(
        [sys.executable, "scripts/seed_dev_data.py"],
        cwd=PROJECT_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "User A token: dev-token-user-a" in result.stdout
    assert database_path.exists()


def test_models_endpoint_rejects_missing_and_invalid_tokens(tmp_path, caplog):
    settings = Settings(database_path=tmp_path / "proxy.sqlite3")
    initialize_database(settings.database_path)
    seed_dev_data(settings.database_path)
    app = create_app(settings)

    caplog.set_level(logging.WARNING)
    with TestClient(app) as client:
        missing_response = client.get("/v1/models")
        invalid_response = client.get(
            "/v1/models", headers={"Authorization": "Bearer not-a-dev-token"}
        )

    assert missing_response.status_code == 401
    assert invalid_response.status_code == 401
    auth_failures = [record for record in caplog.records if record.message == "auth.failure"]
    assert [record.reason for record in auth_failures] == [
        "missing_bearer",
        "invalid_token",
    ]
    assert "not-a-dev-token" not in caplog.text
    assert "Authorization" not in caplog.text


def test_require_user_runs_authentication_in_threadpool(monkeypatch):
    calls = []

    async def fake_to_thread(fn, *args):
        calls.append((fn, args))
        return fn(*args)

    monkeypatch.setattr(deps.asyncio, "to_thread", fake_to_thread)
    auth_service = _FakeAuthService()

    user = asyncio.run(
        deps.require_user(
            HTTPAuthorizationCredentials(scheme="Bearer", credentials="dev-token-user-a"),
            auth_service,
        )
    )

    assert user.id == "user_a"
    assert calls == [(auth_service.authenticate, ("dev-token-user-a",))]


def test_models_routes_forward_to_ollama_and_filter_to_allowlist(tmp_path, monkeypatch):
    settings = Settings(database_path=tmp_path / "proxy.sqlite3")
    initialize_database(settings.database_path)
    seed_dev_data(settings.database_path)
    app = create_app(settings)
    calls = 0

    async def fake_list_models(self):
        nonlocal calls
        calls += 1
        return {
            "object": "list",
            "data": [
                {"id": "llama3.2", "object": "model", "owned_by": "ollama"},
                {"id": "not-allowed", "object": "model", "owned_by": "ollama"},
                {"id": "moondream", "object": "model", "owned_by": "ollama"},
            ],
        }

    monkeypatch.setattr(OllamaClient, "list_models", fake_list_models)

    with TestClient(app) as client:
        v1_response = client.get("/v1/models", headers={"Authorization": "Bearer dev-token-user-a"})
        compatibility_response = client.get(
            "/models", headers={"Authorization": "Bearer dev-token-user-a"}
        )

    assert v1_response.status_code == 200
    assert compatibility_response.status_code == 200
    assert v1_response.json() == {
        "object": "list",
        "data": [
            {"id": "llama3.2", "object": "model", "owned_by": "ollama"},
            {"id": "moondream", "object": "model", "owned_by": "ollama"},
        ],
    }
    assert compatibility_response.json() == v1_response.json()
    assert calls == 2


def test_models_endpoint_returns_clean_error_when_ollama_is_unavailable(tmp_path, caplog):
    settings = Settings(
        database_path=tmp_path / "proxy.sqlite3",
        ollama_base_url="http://127.0.0.1:9/v1",
    )
    initialize_database(settings.database_path)
    seed_dev_data(settings.database_path)
    app = create_app(settings)

    caplog.set_level(logging.WARNING)
    with TestClient(app) as client:
        response = client.get("/v1/models", headers={"Authorization": "Bearer dev-token-user-a"})

    assert response.status_code == 502
    assert response.json() == {
        "error": {
            "message": "Ollama is unavailable",
            "type": "upstream_error",
        }
    }
    upstream_failures = [
        record for record in caplog.records if record.message == "ollama.request_failed"
    ]
    assert len(upstream_failures) == 1
    assert upstream_failures[0].endpoint == "/models"
    assert upstream_failures[0].reason == "unavailable"
    assert "dev-token-user-a" not in caplog.text


class _FakeAuthService:
    def authenticate(self, token: str) -> User | None:
        if token == "dev-token-user-a":
            return User(id="user_a", display_name="User A", role="user")
        return None
