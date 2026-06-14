import logging
from collections.abc import AsyncIterator
from typing import Any

import httpx

from app.errors import UpstreamServiceError

logger = logging.getLogger(__name__)


class OllamaClient:
    def __init__(self, base_url: str, timeout_seconds: float = 30.0) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout_seconds = timeout_seconds

    async def list_models(self) -> dict[str, Any]:
        endpoint = "/models"
        try:
            async with httpx.AsyncClient(
                base_url=self._base_url, timeout=self._timeout_seconds
            ) as client:
                response = await client.get(endpoint)
                response.raise_for_status()
                payload = response.json()
        except (httpx.ConnectError, httpx.TimeoutException, httpx.NetworkError) as exc:
            _log_upstream_failure(
                endpoint,
                reason="unavailable",
                exception_class=exc.__class__.__name__,
            )
            raise UpstreamServiceError("Ollama is unavailable") from exc
        except httpx.HTTPStatusError as exc:
            _log_upstream_failure(endpoint, status_code=exc.response.status_code)
            raise UpstreamServiceError(
                f"Ollama returned HTTP {exc.response.status_code}"
            ) from exc
        except ValueError as exc:
            _log_invalid_response(endpoint, reason="invalid_json")
            raise UpstreamServiceError("Ollama returned invalid JSON") from exc

        if not isinstance(payload, dict):
            _log_invalid_response(endpoint, reason="invalid_shape")
            raise UpstreamServiceError("Ollama returned an invalid models response")

        return payload

    async def create_chat_completion(self, payload: dict[str, Any]) -> dict[str, Any]:
        endpoint = "/chat/completions"
        try:
            async with httpx.AsyncClient(
                base_url=self._base_url, timeout=self._timeout_seconds
            ) as client:
                response = await client.post(endpoint, json=payload)
                response.raise_for_status()
                response_payload = response.json()
        except (httpx.ConnectError, httpx.TimeoutException, httpx.NetworkError) as exc:
            _log_upstream_failure(
                endpoint,
                reason="unavailable",
                exception_class=exc.__class__.__name__,
            )
            raise UpstreamServiceError("Ollama is unavailable") from exc
        except httpx.HTTPStatusError as exc:
            _log_upstream_failure(endpoint, status_code=exc.response.status_code)
            raise UpstreamServiceError(
                f"Ollama returned HTTP {exc.response.status_code}"
            ) from exc
        except ValueError as exc:
            _log_invalid_response(endpoint, reason="invalid_json")
            raise UpstreamServiceError("Ollama returned invalid JSON") from exc

        if not isinstance(response_payload, dict):
            _log_invalid_response(endpoint, reason="invalid_shape")
            raise UpstreamServiceError("Ollama returned an invalid chat response")

        return response_payload

    async def stream_chat_completion(
        self, payload: dict[str, Any]
    ) -> AsyncIterator[bytes]:
        endpoint = "/chat/completions"
        timeout = httpx.Timeout(self._timeout_seconds, read=None)
        try:
            async with httpx.AsyncClient(
                base_url=self._base_url, timeout=timeout
            ) as client:
                async with client.stream(
                    "POST", "/chat/completions", json=payload
                ) as response:
                    response.raise_for_status()
                    async for chunk in response.aiter_bytes():
                        if chunk:
                            yield chunk
        except (httpx.ConnectError, httpx.TimeoutException, httpx.NetworkError) as exc:
            _log_upstream_failure(
                endpoint,
                reason="unavailable",
                exception_class=exc.__class__.__name__,
            )
            raise UpstreamServiceError("Ollama is unavailable") from exc
        except httpx.HTTPStatusError as exc:
            _log_upstream_failure(endpoint, status_code=exc.response.status_code)
            raise UpstreamServiceError(
                f"Ollama returned HTTP {exc.response.status_code}"
            ) from exc


def _log_upstream_failure(
    endpoint: str,
    reason: str | None = None,
    status_code: int | None = None,
    exception_class: str | None = None,
) -> None:
    extra: dict[str, Any] = {"endpoint": endpoint}
    if reason is not None:
        extra["reason"] = reason
    if status_code is not None:
        extra["status_code"] = status_code
    if exception_class is not None:
        extra["exception_class"] = exception_class

    logger.warning("ollama.request_failed", extra=extra)


def _log_invalid_response(endpoint: str, reason: str) -> None:
    logger.warning(
        "ollama.invalid_response",
        extra={"endpoint": endpoint, "reason": reason},
    )
