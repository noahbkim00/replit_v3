import json
import logging
from collections.abc import AsyncIterator
from time import perf_counter
from typing import Any

from app.clients.ollama import OllamaClient
from app.errors import ClientRequestError, UpstreamServiceError
from app.repositories.models import ModelRepository
from app.repositories.usage import TokenUsage, UsageRepository
from app.repositories.users import User
from app.services.limits import LimitService

logger = logging.getLogger(__name__)


class ChatProxyService:
    def __init__(
        self,
        model_repository: ModelRepository,
        ollama_client: OllamaClient,
        usage_repository: UsageRepository,
        limit_service: LimitService,
    ) -> None:
        self._model_repository = model_repository
        self._ollama_client = ollama_client
        self._usage_repository = usage_repository
        self._limit_service = limit_service

    async def create_chat_completion(
        self, user: User, request_body: dict[str, Any]
    ) -> dict[str, Any]:
        try:
            model = self._validate_request(request_body)
            self._limit_service.check_chat_request(user, model, request_body)
        except ClientRequestError as exc:
            logger.warning(
                "chat.failed",
                extra={
                    "user_id": user.id,
                    "model": self._safe_model(request_body),
                    "stream": False,
                    "error_type": exc.error_type,
                    "status_code": exc.status_code,
                },
            )
            raise

        started_at = perf_counter()
        try:
            response_body = await self._ollama_client.create_chat_completion(
                request_body
            )
        except UpstreamServiceError:
            latency_ms = (perf_counter() - started_at) * 1000
            logger.error(
                "chat.failed",
                extra={
                    "user_id": user.id,
                    "model": model,
                    "stream": False,
                    "error_type": "upstream_error",
                    "latency_ms": round(latency_ms, 2),
                },
            )
            raise

        latency_ms = (perf_counter() - started_at) * 1000
        usage = self._extract_usage(response_body)

        self._usage_repository.record_chat_completion(
            user_id=user.id,
            model=model,
            usage=usage,
            latency_ms=latency_ms,
            status="success",
        )
        logger.info(
            "chat.completed",
            extra={
                "user_id": user.id,
                "model": model,
                "stream": False,
                "status": "success",
                "prompt_tokens": usage.prompt_tokens,
                "completion_tokens": usage.completion_tokens,
                "total_tokens": usage.total_tokens,
                "latency_ms": round(latency_ms, 2),
            },
        )
        return response_body

    async def stream_chat_completion(
        self, user: User, request_body: dict[str, Any]
    ) -> AsyncIterator[bytes]:
        model = self._validate_request(request_body)
        stream_payload = self._with_stream_usage(request_body)
        self._limit_service.check_chat_request(user, model, stream_payload)

        started_at = perf_counter()
        usage: TokenUsage | None = None
        pending_text = ""

        try:
            async for chunk in self._ollama_client.stream_chat_completion(
                stream_payload
            ):
                pending_text, usage = self._capture_stream_usage(
                    chunk=chunk,
                    pending_text=pending_text,
                    usage=usage,
                )
                yield chunk
        except UpstreamServiceError:
            latency_ms = (perf_counter() - started_at) * 1000
            logger.error(
                "chat.stream_failed",
                extra={
                    "user_id": user.id,
                    "model": model,
                    "error_type": "upstream_error",
                    "latency_ms": round(latency_ms, 2),
                },
            )
            raise

        latency_ms = (perf_counter() - started_at) * 1000
        if usage is not None:
            self._usage_repository.record_chat_completion(
                user_id=user.id,
                model=model,
                usage=usage,
                latency_ms=latency_ms,
                status="success",
            )
            logger.info(
                "chat.stream_completed",
                extra={
                    "user_id": user.id,
                    "model": model,
                    "stream": True,
                    "prompt_tokens": usage.prompt_tokens,
                    "completion_tokens": usage.completion_tokens,
                    "total_tokens": usage.total_tokens,
                    "latency_ms": round(latency_ms, 2),
                },
            )
        else:
            logger.warning(
                "chat.stream_completed_without_usage",
                extra={
                    "user_id": user.id,
                    "model": model,
                    "latency_ms": round(latency_ms, 2),
                },
            )

    def is_streaming_request(self, request_body: dict[str, Any]) -> bool:
        return request_body.get("stream") is True

    def _validate_request(self, request_body: dict[str, Any]) -> str:
        model = request_body.get("model")
        if not isinstance(model, str) or not model:
            raise ClientRequestError("Request body must include a model")

        allowed_model_ids = self._model_repository.list_allowed_model_ids()
        if model not in allowed_model_ids:
            raise ClientRequestError(f"Model '{model}' is not allowed")

        self._validate_vision_content(request_body)
        return model

    def _safe_model(self, request_body: dict[str, Any]) -> str | None:
        model = request_body.get("model")
        if isinstance(model, str):
            return model
        return None

    def _with_stream_usage(self, request_body: dict[str, Any]) -> dict[str, Any]:
        stream_options = request_body.get("stream_options")
        if not isinstance(stream_options, dict):
            stream_options = {}

        return {
            **request_body,
            "stream_options": {
                **stream_options,
                "include_usage": True,
            },
        }

    def _capture_stream_usage(
        self,
        chunk: bytes,
        pending_text: str,
        usage: TokenUsage | None,
    ) -> tuple[str, TokenUsage | None]:
        text = pending_text + chunk.decode("utf-8", errors="ignore")
        lines = text.split("\n")
        pending_text = lines.pop()

        for line in lines:
            data = self._sse_data(line)
            if data is None or data == "[DONE]":
                continue

            try:
                payload = json.loads(data)
            except json.JSONDecodeError:
                continue

            if isinstance(payload, dict) and isinstance(payload.get("usage"), dict):
                usage = self._extract_usage(payload)

        return pending_text, usage

    def _sse_data(self, line: str) -> str | None:
        stripped = line.strip()
        if not stripped.startswith("data:"):
            return None
        return stripped.removeprefix("data:").strip()

    def _validate_vision_content(self, request_body: dict[str, Any]) -> None:
        messages = request_body.get("messages")
        if not isinstance(messages, list):
            return

        for message in messages:
            if not isinstance(message, dict):
                continue
            content = message.get("content")
            if not isinstance(content, list):
                continue
            for part in content:
                if isinstance(part, dict) and part.get("type") == "image_url":
                    self._validate_image_part(part)

    def _validate_image_part(self, part: dict[str, Any]) -> None:
        image_url = part.get("image_url")
        if not isinstance(image_url, dict):
            raise ClientRequestError("image_url content must include an image_url object")

        url = image_url.get("url")
        if not isinstance(url, str) or not url:
            raise ClientRequestError("image_url content must include a url")

        if not url.startswith("data:image/") or ";base64," not in url:
            raise ClientRequestError(
                "Remote image URLs are not supported; send a base64 data URL"
            )

    def _extract_usage(self, response_body: dict[str, Any]) -> TokenUsage:
        usage = response_body.get("usage")
        if not isinstance(usage, dict):
            return TokenUsage(prompt_tokens=0, completion_tokens=0, total_tokens=0)

        prompt_tokens = self._usage_int(usage.get("prompt_tokens"))
        completion_tokens = self._usage_int(usage.get("completion_tokens"))
        total_tokens = self._usage_int(usage.get("total_tokens"))
        if total_tokens == 0:
            total_tokens = prompt_tokens + completion_tokens

        return TokenUsage(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
        )

    def _usage_int(self, value: Any) -> int:
        if isinstance(value, bool):
            return 0
        if isinstance(value, int):
            return max(value, 0)
        return 0
