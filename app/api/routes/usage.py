from typing import Annotated, Any

from fastapi import APIRouter, Depends

from app.api.deps import get_usage_service, require_user
from app.repositories.users import User
from app.services.usage import UsageService

router = APIRouter()


@router.get("/usage")
def get_usage(
    user: Annotated[User, Depends(require_user)],
    usage_service: Annotated[UsageService, Depends(get_usage_service)],
) -> dict[str, Any]:
    return usage_service.get_usage_summary(user.id)


@router.get("/usage/events")
def get_usage_events(
    user: Annotated[User, Depends(require_user)],
    usage_service: Annotated[UsageService, Depends(get_usage_service)],
) -> dict[str, Any]:
    return usage_service.list_usage_events(user.id)
