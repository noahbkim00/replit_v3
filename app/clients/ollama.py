from collections.abc import AsyncIterator
from typing import Any

import httpx

from app.errors import UpstreamServiceError


class OllamaClient:
    def __init__(self, base_url: str, timeout_seconds: float = 10.0) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout_seconds = timeout_seconds

    async def list_models(self) -> dict[str, Any]:
        try:
            async with httpx.AsyncClient(
                base_url=self._base_url, timeout=self._timeout_seconds
            ) as client:
                response = await client.get("/models")
                response.raise_for_status()
                payload = response.json()
        except (httpx.ConnectError, httpx.TimeoutException, httpx.NetworkError) as exc:
            raise UpstreamServiceError("Ollama is unavailable") from exc
        except httpx.HTTPStatusError as exc:
            raise UpstreamServiceError(
                f"Ollama returned HTTP {exc.response.status_code}"
            ) from exc
        except ValueError as exc:
            raise UpstreamServiceError("Ollama returned invalid JSON") from exc

        if not isinstance(payload, dict):
            raise UpstreamServiceError("Ollama returned an invalid models response")

        return payload

    async def create_chat_completion(self, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            async with httpx.AsyncClient(
                base_url=self._base_url, timeout=self._timeout_seconds
            ) as client:
                response = await client.post("/chat/completions", json=payload)
                response.raise_for_status()
                response_payload = response.json()
        except (httpx.ConnectError, httpx.TimeoutException, httpx.NetworkError) as exc:
            raise UpstreamServiceError("Ollama is unavailable") from exc
        except httpx.HTTPStatusError as exc:
            raise UpstreamServiceError(
                f"Ollama returned HTTP {exc.response.status_code}"
            ) from exc
        except ValueError as exc:
            raise UpstreamServiceError("Ollama returned invalid JSON") from exc

        if not isinstance(response_payload, dict):
            raise UpstreamServiceError("Ollama returned an invalid chat response")

        return response_payload

    async def stream_chat_completion(
        self, payload: dict[str, Any]
    ) -> AsyncIterator[bytes]:
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
            raise UpstreamServiceError("Ollama is unavailable") from exc
        except httpx.HTTPStatusError as exc:
            raise UpstreamServiceError(
                f"Ollama returned HTTP {exc.response.status_code}"
            ) from exc
