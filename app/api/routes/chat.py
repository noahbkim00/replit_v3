from typing import Annotated, Any

from fastapi import APIRouter, Body, Depends

from app.api.deps import get_chat_proxy_service, require_user
from app.repositories.users import User
from app.services.chat_proxy import ChatProxyService

router = APIRouter()


@router.post("/v1/chat/completions")
@router.post("/chat/completions")
async def create_chat_completion(
    request_body: Annotated[dict[str, Any], Body(...)],
    user: Annotated[User, Depends(require_user)],
    chat_proxy_service: Annotated[ChatProxyService, Depends(get_chat_proxy_service)],
) -> dict[str, Any]:
    return await chat_proxy_service.create_chat_completion(user, request_body)
