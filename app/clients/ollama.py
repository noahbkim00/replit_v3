from typing import Any

import httpx

from app.core.errors import UpstreamTimeoutError, UpstreamUnavailableError


class OllamaClient:
    """Boundary for Ollama API calls."""

    def __init__(
        self,
        base_url: str,
        *,
        http_client: httpx.AsyncClient | None = None,
        timeout_seconds: float = 30.0,
    ) -> None:
        self._base_url = base_url.rstrip("/") + "/"
        self._http_client = http_client or httpx.AsyncClient(
            base_url=self._base_url,
            timeout=timeout_seconds,
        )

    async def __aenter__(self) -> "OllamaClient":
        return self

    async def __aexit__(self, exc_type: object, exc: object, traceback: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        await self._http_client.aclose()

    async def list_models(self) -> dict[str, Any]:
        try:
            response = await self._http_client.get("models")
            response.raise_for_status()
        except httpx.TimeoutException as exc:
            raise UpstreamTimeoutError() from exc
        except httpx.HTTPStatusError as exc:
            raise UpstreamUnavailableError(
                f"Ollama returned HTTP {exc.response.status_code}"
            ) from exc
        except httpx.RequestError as exc:
            raise UpstreamUnavailableError() from exc

        return response.json()
