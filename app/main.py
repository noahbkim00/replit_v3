from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from starlette.requests import Request
from starlette.responses import JSONResponse

from app.api.router import api_router
from app.clients.ollama import OllamaClient
from app.core.config import Settings, get_settings
from app.core.errors import ProxyError
from app.middleware.request_id import RequestIDMiddleware
from app.middleware.request_size import RequestSizeLimitMiddleware
from app.schemas.errors import ErrorDetail, ErrorEnvelope
from app.services.model_service import ModelService


def create_app(
    settings: Settings | None = None,
    ollama_client: OllamaClient | None = None,
) -> FastAPI:
    resolved_settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        resolved_ollama_client = ollama_client or OllamaClient(
            base_url=resolved_settings.ollama_base_url,
        )
        app.state.ollama_client = resolved_ollama_client
        app.state.model_service = ModelService(resolved_ollama_client)
        try:
            yield
        finally:
            await resolved_ollama_client.aclose()

    app = FastAPI(
        title="FastAPI Ollama Proxy",
        version="0.1.0",
        lifespan=lifespan,
    )
    app.state.settings = resolved_settings

    @app.exception_handler(ProxyError)
    async def proxy_error_handler(_request: Request, exc: ProxyError) -> JSONResponse:
        envelope = ErrorEnvelope(
            error=ErrorDetail(
                message=exc.message,
                type=exc.error_type,
                code=exc.code,
            )
        )
        return JSONResponse(
            status_code=exc.status_code,
            content=envelope.model_dump(exclude_none=True),
        )

    app.add_middleware(RequestIDMiddleware)
    app.add_middleware(
        RequestSizeLimitMiddleware,
        max_body_size=resolved_settings.max_request_body_bytes,
    )
    app.include_router(api_router)

    return app


app = create_app()
