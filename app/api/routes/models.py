from typing import Annotated, Any

from fastapi import APIRouter, Depends

from app.api.deps import get_model_service, require_user
from app.repositories.users import User
from app.services.models import ModelService

router = APIRouter()


@router.get("/v1/models")
@router.get("/models")
async def list_models(
    _: Annotated[User, Depends(require_user)],
    model_service: Annotated[ModelService, Depends(get_model_service)],
) -> dict[str, Any]:
    return await model_service.list_models()
