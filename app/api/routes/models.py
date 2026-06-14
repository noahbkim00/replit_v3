from typing import Annotated, Any

from fastapi import APIRouter, Depends

from app.api.deps import get_model_service
from app.services.model_service import ModelService

router = APIRouter(tags=["models"])


@router.get("/v1/models")
@router.get("/models")
async def list_models(
    model_service: Annotated[ModelService, Depends(get_model_service)],
) -> dict[str, Any]:
    return await model_service.list_models()
