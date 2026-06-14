from fastapi import Request

from app.core.config import Settings, get_settings
from app.services.model_service import ModelService


def get_app_settings() -> Settings:
    return get_settings()


def get_model_service(request: Request) -> ModelService:
    return request.app.state.model_service
