from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.clients.ollama import OllamaClient
from app.config import Settings
from app.repositories.models import ModelRepository
from app.repositories.usage import UsageRepository
from app.repositories.users import User, UserRepository
from app.services.auth import AuthService
from app.services.chat_proxy import ChatProxyService
from app.services.limits import LimitService
from app.services.models import ModelService

bearer_scheme = HTTPBearer(auto_error=False)


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_auth_service(settings: Annotated[Settings, Depends(get_settings)]) -> AuthService:
    return AuthService(UserRepository(settings.database_path))


def get_model_service(settings: Annotated[Settings, Depends(get_settings)]) -> ModelService:
    return ModelService(
        model_repository=ModelRepository(settings.database_path),
        ollama_client=OllamaClient(settings.ollama_base_url),
    )


def get_chat_proxy_service(
    settings: Annotated[Settings, Depends(get_settings)],
) -> ChatProxyService:
    return ChatProxyService(
        model_repository=ModelRepository(settings.database_path),
        ollama_client=OllamaClient(settings.ollama_base_url),
        usage_repository=UsageRepository(settings.database_path),
        limit_service=LimitService(),
    )


async def require_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
) -> User:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user = auth_service.authenticate(credentials.credentials)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return user
