from typing import Any

from app.clients.ollama import OllamaClient


class ModelService:
    """Coordinates model metadata access."""

    def __init__(self, ollama_client: OllamaClient) -> None:
        self._ollama_client = ollama_client

    async def list_models(self) -> dict[str, Any]:
        return await self._ollama_client.list_models()
