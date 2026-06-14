import json
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse

from app.api.deps import get_chat_proxy_service, require_user
from app.config import Settings
from app.errors import ClientRequestError
from app.repositories.users import User
from app.services.chat_proxy import ChatProxyService

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


async def _read_json_body(
    request: Request, max_request_body_bytes: int
) -> dict[str, Any]:
    content_length = request.headers.get("content-length")
    if content_length is not None and int(content_length) > max_request_body_bytes:
        raise ClientRequestError(
            "Request body exceeds the configured size limit", status_code=413
        )

    body = await request.body()
    if len(body) > max_request_body_bytes:
        raise ClientRequestError(
            "Request body exceeds the configured size limit", status_code=413
        )

    try:
        payload = json.loads(body)
    except json.JSONDecodeError as exc:
        raise ClientRequestError("Request body must be valid JSON") from exc

    if not isinstance(payload, dict):
        raise ClientRequestError("Request body must be a JSON object")

    return payload
