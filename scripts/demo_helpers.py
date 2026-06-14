import argparse
import base64
import json
from typing import Any

import httpx
from openai import OpenAI


class DemoFailure(Exception):
    pass


def add_common_args(
    parser: argparse.ArgumentParser,
    *,
    include_admin: bool = False,
    include_models: bool = True,
) -> None:
    parser.add_argument("--proxy-url", default="http://127.0.0.1:8000")
    parser.add_argument("--api-key", default="dev-token-user-a")
    parser.add_argument("--timeout-seconds", type=float, default=90.0)
    if include_admin:
        parser.add_argument("--admin-api-key", default="dev-token-admin")
    if include_models:
        parser.add_argument("--text-model", default="llama3.2:1b")
        parser.add_argument("--vision-model", default="moondream")


def proxy_url(value: str) -> str:
    return value.rstrip("/")


def auth_headers(api_key: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {api_key}"}


def build_openai_client(proxy: str, api_key: str, timeout_seconds: float) -> OpenAI:
    return OpenAI(
        base_url=f"{proxy_url(proxy)}/v1",
        api_key=api_key,
        timeout=timeout_seconds,
    )


def http_client(proxy: str, timeout_seconds: float) -> httpx.Client:
    return httpx.Client(base_url=proxy_url(proxy), timeout=timeout_seconds)


def preflight_models(
    *,
    proxy: str,
    api_key: str,
    required_models: list[str],
    timeout_seconds: float,
) -> None:
    try:
        with http_client(proxy, timeout_seconds) as client:
            response = client.get("/v1/models", headers=auth_headers(api_key))
    except httpx.HTTPError as exc:
        raise DemoFailure(f"Proxy is not reachable at {proxy_url(proxy)}: {exc}") from exc

    if response.status_code == 502 and _error_type(response) == "upstream_error":
        raise DemoFailure("Ollama is unavailable. Start it with: ollama serve")
    if response.status_code >= 400:
        raise DemoFailure(f"Model preflight failed: HTTP {response.status_code} {response.text}")

    installed = {
        item.get("id")
        for item in response.json().get("data", [])
        if isinstance(item, dict) and isinstance(item.get("id"), str)
    }
    missing = [
        model
        for model in required_models
        if model not in installed and f"{model}:latest" not in installed
    ]
    if missing:
        pulls = "\n".join(f"ollama pull {model}" for model in missing)
        raise DemoFailure(f"Required model(s) missing from proxy model list: {missing}\n{pulls}")


def fetch_image_data_url(url: str, timeout_seconds: float) -> str:
    try:
        response = httpx.get(url, timeout=timeout_seconds, follow_redirects=True)
        response.raise_for_status()
    except httpx.HTTPError as exc:
        raise DemoFailure(f"Could not fetch demo image from {url}: {exc}") from exc

    content_type = response.headers.get("content-type", "image/jpeg").split(";")[0]
    encoded = base64.b64encode(response.content).decode("ascii")
    return f"data:{content_type};base64,{encoded}"


def text_messages(prompt: str) -> list[dict[str, Any]]:
    return [
        {"role": "system", "content": "You are a concise assistant."},
        {"role": "user", "content": prompt},
    ]


def vision_messages(prompt: str, image_data_url: str) -> list[dict[str, Any]]:
    return [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": image_data_url}},
            ],
        }
    ]


def usage_total_tokens(usage: Any) -> int | None:
    if usage is None:
        return None
    if isinstance(usage, dict):
        value = usage.get("total_tokens")
    else:
        value = getattr(usage, "total_tokens", None)
    return value if isinstance(value, int) else None


def usage_request_count(summary: dict[str, Any]) -> int:
    aggregate = summary.get("aggregate", {})
    if not isinstance(aggregate, dict):
        return 0
    value = aggregate.get("request_count")
    return value if isinstance(value, int) else 0


def print_pass(name: str, **fields: Any) -> None:
    details = " ".join(f"{key}={value}" for key, value in fields.items())
    print(f"{name} PASS {details}".rstrip())


def print_fail(name: str, message: str) -> None:
    print(f"{name} FAIL {message}")


def get_usage(client: httpx.Client, api_key: str) -> dict[str, Any]:
    response = client.get("/usage", headers=auth_headers(api_key))
    response.raise_for_status()
    return response.json()


def get_usage_events(client: httpx.Client, api_key: str) -> dict[str, Any]:
    response = client.get("/usage/events", headers=auth_headers(api_key))
    response.raise_for_status()
    return response.json()


def get_admin_usage(client: httpx.Client, admin_api_key: str, user_id: str) -> dict[str, Any]:
    response = client.get(f"/admin/users/{user_id}/usage", headers=auth_headers(admin_api_key))
    response.raise_for_status()
    return response.json()


def get_limits(client: httpx.Client, admin_api_key: str, user_id: str) -> dict[str, Any]:
    response = client.get(f"/admin/users/{user_id}/limits", headers=auth_headers(admin_api_key))
    response.raise_for_status()
    return response.json()


def set_limits(
    client: httpx.Client,
    admin_api_key: str,
    user_id: str,
    *,
    requests_per_minute: int | None,
    daily_tokens: int | None = None,
    total_tokens: int | None = None,
) -> dict[str, Any]:
    response = client.put(
        f"/admin/users/{user_id}/limits",
        headers=auth_headers(admin_api_key),
        json={
            "requests_per_minute": requests_per_minute,
            "daily_tokens": daily_tokens,
            "total_tokens": total_tokens,
        },
    )
    response.raise_for_status()
    return response.json()


def clear_limits(client: httpx.Client, admin_api_key: str, user_id: str) -> dict[str, Any]:
    return set_limits(
        client,
        admin_api_key,
        user_id,
        requests_per_minute=None,
        daily_tokens=None,
        total_tokens=None,
    )


def error_type_from_exception(exc: Exception) -> str | None:
    response = getattr(exc, "response", None)
    if response is None:
        return None
    try:
        payload = response.json()
    except (json.JSONDecodeError, ValueError):
        return None
    error = payload.get("error") if isinstance(payload, dict) else None
    if not isinstance(error, dict):
        return None
    error_type = error.get("type")
    return error_type if isinstance(error_type, str) else None


def _error_type(response: httpx.Response) -> str | None:
    try:
        payload = response.json()
    except json.JSONDecodeError:
        return None
    error = payload.get("error") if isinstance(payload, dict) else None
    if not isinstance(error, dict):
        return None
    error_type = error.get("type")
    return error_type if isinstance(error_type, str) else None
