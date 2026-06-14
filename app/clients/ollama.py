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
