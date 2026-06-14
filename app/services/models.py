import asyncio
from typing import Any

from app.clients.ollama import OllamaClient
from app.errors import UpstreamServiceError
from app.repositories.models import ModelRepository


class ModelService:
    def __init__(self, model_repository: ModelRepository, ollama_client: OllamaClient) -> None:
        self._model_repository = model_repository
        self._ollama_client = ollama_client

    async def list_models(self) -> dict[str, Any]:
        allowed_model_ids = await asyncio.to_thread(self._model_repository.list_allowed_model_ids)
        upstream_payload = await self._ollama_client.list_models()
        upstream_models = upstream_payload.get("data")

        if not isinstance(upstream_models, list):
            raise UpstreamServiceError("Ollama returned an invalid models response")

        filtered_models = [
            model
            for model in upstream_models
            if isinstance(model, dict)
            and self._is_allowed_model_id(model.get("id"), allowed_model_ids)
        ]

        return {
            **upstream_payload,
            "object": upstream_payload.get("object", "list"),
            "data": filtered_models,
        }

    def _is_allowed_model_id(self, model_id: Any, allowed_model_ids: set[str]) -> bool:
        if not isinstance(model_id, str):
            return False
        return model_id in allowed_model_ids or (
            model_id.endswith(":latest") and model_id.removesuffix(":latest") in allowed_model_ids
        )
