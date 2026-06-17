import sqlite3
from typing import Any

from fastapi.testclient import TestClient

from app.clients.ollama import OllamaClient
from app.repositories.limits import LimitRepository
from app.repositories.usage import TokenUsage, UsageRepository
from app.repositories.users import UserRepository


def test_authenticated_user_usage_report_renders_usage_limits_and_recent_events(
    seeded_app, user_headers
):
    app, database_path = seeded_app()
    usage_repository = UsageRepository(database_path)
    limit_repository = LimitRepository(database_path)
    usage_repository.record_chat_completion(
        user_id="user_a",
        model="llama3.2:1b",
        usage=TokenUsage(prompt_tokens=3, completion_tokens=2, total_tokens=5),
        latency_ms=12.34,
        status="success",
    )
    limit_repository.update_user_limits(
        user_id="user_a",
        requests_per_minute=7,
        daily_tokens=100,
        total_tokens=250,
    )

    with TestClient(app) as client:
        response = client.get("/usage/report", headers=user_headers("dev-token-user-a"))

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "Usage Report for user_a" in response.text
    assert "Requests per minute" in response.text
    assert "Daily tokens" in response.text
    assert "Total tokens" in response.text
    assert "llama3.2:1b" in response.text
    assert "success" in response.text
    assert "12.3" in response.text
    assert "Admin view" not in response.text


def test_usage_report_is_scoped_to_authenticated_user(seeded_app, user_headers):
    app, database_path = seeded_app()
    usage_repository = UsageRepository(database_path)
    usage_repository.record_chat_completion(
        user_id="user_a",
        model="llama3.2:1b",
        usage=TokenUsage(prompt_tokens=3, completion_tokens=2, total_tokens=5),
        latency_ms=10,
        status="success",
    )
    usage_repository.record_chat_completion(
        user_id="user_b",
        model="moondream",
        usage=TokenUsage(prompt_tokens=11, completion_tokens=13, total_tokens=24),
        latency_ms=20,
        status="user-b-private-status",
    )

    with TestClient(app) as client:
        response = client.get("/usage/report", headers=user_headers("dev-token-user-a"))

    assert response.status_code == 200
    assert "Usage Report for user_a" in response.text
    assert "llama3.2:1b" in response.text
    assert "moondream" not in response.text
    assert "user-b-private-status" not in response.text


def test_usage_report_requires_bearer_auth(seeded_app):
    app, _database_path = seeded_app()

    with TestClient(app) as client:
        missing_response = client.get("/usage/report")
        invalid_response = client.get(
            "/usage/report", headers={"Authorization": "Bearer not-a-real-token"}
        )

    assert missing_response.status_code == 401
    assert invalid_response.status_code == 401


def test_usage_report_escapes_dynamic_values(seeded_app, user_headers):
    app, database_path = seeded_app()
    usage_repository = UsageRepository(database_path)
    usage_repository.record_chat_completion(
        user_id="user_a",
        model='<script>alert("model")</script>',
        usage=TokenUsage(prompt_tokens=1, completion_tokens=1, total_tokens=2),
        latency_ms=1,
        status='<script>alert("status")</script>',
    )

    with TestClient(app) as client:
        response = client.get("/usage/report", headers=user_headers("dev-token-user-a"))

    assert response.status_code == 200
    assert "<script>" not in response.text
    assert "&lt;script&gt;alert(&quot;model&quot;)&lt;/script&gt;" in response.text
    assert "&lt;script&gt;alert(&quot;status&quot;)&lt;/script&gt;" in response.text


def test_empty_usage_report_renders_cleanly(seeded_app, user_headers):
    app, _database_path = seeded_app()

    with TestClient(app) as client:
        response = client.get("/usage/report", headers=user_headers("dev-token-user-a"))

    assert response.status_code == 200
    assert "Usage Report for user_a" in response.text
    assert "No model usage yet" in response.text
    assert "No recent events yet" in response.text
    assert response.text.count("Not configured") == 3


def test_usage_report_limits_recent_events_to_latest_25(seeded_app, user_headers):
    app, database_path = seeded_app()
    usage_repository = UsageRepository(database_path)
    for index in range(30):
        usage_repository.record_chat_completion(
            user_id="user_a",
            model="llama3.2:1b",
            usage=TokenUsage(prompt_tokens=1, completion_tokens=1, total_tokens=2),
            latency_ms=index,
            status=f"status-{index}",
        )

    with TestClient(app) as client:
        response = client.get("/usage/report", headers=user_headers("dev-token-user-a"))

    assert response.status_code == 200
    assert "status-29" in response.text
    assert "status-5" in response.text
    assert "status-4" not in response.text


def test_admin_can_open_read_only_usage_report_for_user(seeded_app, user_headers):
    app, database_path = seeded_app()
    usage_repository = UsageRepository(database_path)
    usage_repository.record_chat_completion(
        user_id="user_a",
        model="llama3.2:1b",
        usage=TokenUsage(prompt_tokens=3, completion_tokens=2, total_tokens=5),
        latency_ms=10,
        status="success",
    )
    usage_repository.record_chat_completion(
        user_id="user_b",
        model="moondream",
        usage=TokenUsage(prompt_tokens=11, completion_tokens=13, total_tokens=24),
        latency_ms=20,
        status="success",
    )

    with TestClient(app) as client:
        non_admin_response = client.get(
            "/admin/users/user_a/usage/report", headers=user_headers("dev-token-user-a")
        )
        admin_response = client.get(
            "/admin/users/user_a/usage/report", headers=user_headers("dev-token-admin")
        )

    assert non_admin_response.status_code == 403
    assert admin_response.status_code == 200
    assert admin_response.headers["content-type"].startswith("text/html")
    assert "Admin Usage Report for user_a" in admin_response.text
    assert "Admin view" in admin_response.text
    assert "llama3.2:1b" in admin_response.text
    assert "moondream" not in admin_response.text


def test_admin_usage_report_lists_associated_users_with_real_prompt_usage(
    seeded_app, user_headers, monkeypatch
):
    app, database_path = seeded_app()
    user_repository = UserRepository(database_path)
    created_users = (
        ("portfolio_admin", "Portfolio Admin", "admin", "dev-token-portfolio-admin"),
        ("managed_alpha", "Managed Alpha", "user", "dev-token-managed-alpha"),
        ("managed_beta", "Managed Beta", "user", "dev-token-managed-beta"),
        ("unmanaged_user", "Unmanaged User", "user", "dev-token-unmanaged-user"),
    )
    for user_id, display_name, role, token in created_users:
        user_repository.upsert_user(user_id, display_name, role=role)
        user_repository.upsert_api_token(token, user_id, token, f"{display_name} token")

    user_repository.upsert_admin_user_association("portfolio_admin", "managed_alpha")
    user_repository.upsert_admin_user_association("portfolio_admin", "managed_beta")

    prompt_usage = {
        "alpha first prompt": {"prompt_tokens": 4, "completion_tokens": 2, "total_tokens": 6},
        "alpha second prompt": {"prompt_tokens": 5, "completion_tokens": 3, "total_tokens": 8},
        "beta prompt": {"prompt_tokens": 7, "completion_tokens": 1, "total_tokens": 8},
        "unmanaged prompt": {"prompt_tokens": 11, "completion_tokens": 2, "total_tokens": 13},
    }

    async def fake_create_chat_completion(
        _self: OllamaClient, payload: dict[str, Any]
    ) -> dict[str, Any]:
        prompt = payload["messages"][0]["content"]
        return {
            "id": "chatcmpl-report-test",
            "object": "chat.completion",
            "model": payload["model"],
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": "ok"},
                    "finish_reason": "stop",
                }
            ],
            "usage": prompt_usage[prompt],
        }

    monkeypatch.setattr(OllamaClient, "create_chat_completion", fake_create_chat_completion)

    def send_prompt(client: TestClient, token: str, prompt: str):
        return client.post(
            "/v1/chat/completions",
            headers=user_headers(token),
            json={
                "model": "llama3.2:1b",
                "messages": [{"role": "user", "content": prompt}],
            },
        )

    with TestClient(app) as client:
        assert (
            send_prompt(client, "dev-token-managed-alpha", "alpha first prompt").status_code == 200
        )
        assert (
            send_prompt(client, "dev-token-managed-alpha", "alpha second prompt").status_code == 200
        )
        assert send_prompt(client, "dev-token-managed-beta", "beta prompt").status_code == 200
        assert (
            send_prompt(client, "dev-token-unmanaged-user", "unmanaged prompt").status_code == 200
        )

        admin_response = client.get(
            "/admin/usage/report",
            headers=user_headers("dev-token-portfolio-admin"),
        )
        detail_response = client.get(
            "/admin/users/managed_alpha/usage/report",
            headers=user_headers("dev-token-portfolio-admin"),
        )
        forbidden_detail_response = client.get(
            "/admin/users/unmanaged_user/usage/report",
            headers=user_headers("dev-token-portfolio-admin"),
        )
        non_admin_response = client.get(
            "/admin/usage/report",
            headers=user_headers("dev-token-managed-alpha"),
        )

    assert admin_response.status_code == 200
    assert admin_response.headers["content-type"].startswith("text/html")
    assert "Admin Usage Report for portfolio_admin" in admin_response.text
    assert "Associated Users" in admin_response.text
    assert "Associated users" in admin_response.text
    assert "Recent Associated User Events" in admin_response.text
    assert (
        "<td>managed_alpha</td><td>Managed Alpha</td><td>user</td>"
        "<td>2</td><td>9</td><td>5</td><td>14</td>"
    ) in admin_response.text
    assert (
        "<td>managed_beta</td><td>Managed Beta</td><td>user</td>"
        "<td>1</td><td>7</td><td>1</td><td>8</td>"
    ) in admin_response.text
    assert "unmanaged_user" not in admin_response.text
    assert "Unmanaged User" not in admin_response.text
    assert "dev-token-portfolio-admin" not in admin_response.text

    assert detail_response.status_code == 200
    assert "Admin Usage Report for managed_alpha" in detail_response.text
    assert "managed_beta" not in detail_response.text
    assert forbidden_detail_response.status_code == 403
    assert forbidden_detail_response.json()["error"]["type"] == "permission_denied"
    assert non_admin_response.status_code == 403


def test_usage_report_browser_shell_is_no_data_and_fetches_with_bearer_auth(seeded_app):
    app, _database_path = seeded_app()

    with TestClient(app) as client:
        response = client.get("/usage/report/browser")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "/usage/report" in response.text
    assert "/admin/usage/report" in response.text
    assert "target-user-id" not in response.text
    assert '"Authorization": `Bearer ${token}`' in response.text
    assert 'sandbox=""' in response.text
    assert "srcdoc" in response.text
    assert "?token=" not in response.text
    assert "localStorage" not in response.text
    assert "sessionStorage" not in response.text
    assert "document.cookie" not in response.text
    assert "dev-token-user-a" not in response.text
    assert "dev-token-admin" not in response.text
    assert "dev-token-demo-report" not in response.text


def test_recent_usage_repository_handles_zero_limit(seeded_app):
    _app, database_path = seeded_app()
    usage_repository = UsageRepository(database_path)
    usage_repository.record_chat_completion(
        user_id="user_a",
        model="llama3.2:1b",
        usage=TokenUsage(prompt_tokens=1, completion_tokens=1, total_tokens=2),
        latency_ms=1,
        status="success",
    )

    assert usage_repository.list_recent_usage_events("user_a", 0) == []


def test_report_does_not_render_token_values(seeded_app, user_headers):
    app, database_path = seeded_app()
    with sqlite3.connect(database_path) as connection:
        token_rows = connection.execute("SELECT token_hash FROM api_tokens").fetchall()

    with TestClient(app) as client:
        response = client.get("/usage/report", headers=user_headers("dev-token-user-a"))

    assert response.status_code == 200
    for (token_hash,) in token_rows:
        assert token_hash not in response.text
    assert "dev-token-user-a" not in response.text
