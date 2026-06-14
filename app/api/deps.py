import logging
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.clients.ollama import OllamaClient
from app.config import Settings
from app.repositories.limits import LimitRepository
from app.repositories.models import ModelRepository
from app.repositories.quota import QuotaRepository
from app.repositories.usage import UsageRepository
from app.repositories.users import User, UserRepository
from app.services.auth import AuthService
from app.services.chat_proxy import ChatProxyService
from app.services.limits import LimitService
from app.services.models import ModelService
from app.services.usage import UsageService

logger = logging.getLogger(__name__)

bearer_scheme = HTTPBearer(auto_error=False)


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_auth_service(settings: Annotated[Settings, Depends(get_settings)]) -> AuthService:
    return AuthService(UserRepository(settings.database_path))


def get_ollama_client(request: Request) -> OllamaClient:
    return request.app.state.ollama_client


def get_model_service(
    settings: Annotated[Settings, Depends(get_settings)],
    ollama_client: Annotated[OllamaClient, Depends(get_ollama_client)],
) -> ModelService:
    return ModelService(
        model_repository=ModelRepository(settings.database_path),
        ollama_client=ollama_client,
    )


def get_chat_proxy_service(
    settings: Annotated[Settings, Depends(get_settings)],
    request: Request,
    ollama_client: Annotated[OllamaClient, Depends(get_ollama_client)],
) -> ChatProxyService:
    return ChatProxyService(
        model_repository=ModelRepository(settings.database_path),
        ollama_client=ollama_client,
        limit_service=LimitService(
            limit_repository=LimitRepository(settings.database_path),
            quota_repository=QuotaRepository(settings.database_path),
        ),
        ollama_concurrency_limiter=request.app.state.ollama_concurrency_limiter,
    )


def get_usage_service(settings: Annotated[Settings, Depends(get_settings)]) -> UsageService:
    return UsageService(UsageRepository(settings.database_path))


def get_limit_service(settings: Annotated[Settings, Depends(get_settings)]) -> LimitService:
    return LimitService(
        limit_repository=LimitRepository(settings.database_path),
        quota_repository=QuotaRepository(settings.database_path),
    )


async def require_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
) -> User:
    if credentials is None or credentials.scheme.lower() != "bearer":
        logger.warning("auth.failure", extra={"reason": "missing_bearer"})
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user = auth_service.authenticate(credentials.credentials)
    if user is None:
        logger.warning("auth.failure", extra={"reason": "invalid_token"})
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return user


async def require_admin(user: Annotated[User, Depends(require_user)]) -> User:
    if not user.is_admin:
        logger.warning("auth.forbidden", extra={"user_id": user.id})
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin credentials required",
        )
    return user
