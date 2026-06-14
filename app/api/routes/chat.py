import json
import logging
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse

from app.api.deps import get_chat_proxy_service, require_user
from app.config import Settings
from app.errors import ClientRequestError
from app.repositories.users import User
from app.services.chat_proxy import ChatProxyService

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/v1/chat/completions")
@router.post("/chat/completions")
async def create_chat_completion(
    request: Request,
    user: Annotated[User, Depends(require_user)],
    chat_proxy_service: Annotated[ChatProxyService, Depends(get_chat_proxy_service)],
):
    settings: Settings = request.app.state.settings
    request_body = await _read_json_body(request, settings.max_request_body_bytes)

    if chat_proxy_service.is_streaming_request(request_body):
        return StreamingResponse(
            chat_proxy_service.stream_chat_completion(user, request_body),
            media_type="text/event-stream",
        )

    return await chat_proxy_service.create_chat_completion(user, request_body)


async def _read_json_body(request: Request, max_request_body_bytes: int) -> dict[str, Any]:
    content_length = request.headers.get("content-length")
    try:
        content_length_value = int(content_length) if content_length is not None else None
    except ValueError:
        content_length_value = None

    if content_length_value is not None and content_length_value > max_request_body_bytes:
        logger.warning(
            "chat.rejected",
            extra={
                "reason": "body_too_large",
                "limit_bytes": max_request_body_bytes,
                "content_length": content_length_value,
            },
        )
        raise ClientRequestError("Request body exceeds the configured size limit", status_code=413)

    body = await request.body()
    if len(body) > max_request_body_bytes:
        logger.warning(
            "chat.rejected",
            extra={
                "reason": "body_too_large",
                "limit_bytes": max_request_body_bytes,
                "content_length": content_length_value,
            },
        )
        raise ClientRequestError("Request body exceeds the configured size limit", status_code=413)

    try:
        payload = json.loads(body)
    except json.JSONDecodeError as exc:
        logger.warning("chat.rejected", extra={"reason": "invalid_json"})
        raise ClientRequestError("Request body must be valid JSON") from exc

    if not isinstance(payload, dict):
        logger.warning("chat.rejected", extra={"reason": "body_not_object"})
        raise ClientRequestError("Request body must be a JSON object")

    return payload
