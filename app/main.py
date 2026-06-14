import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.api.router import api_router
from app.config import Settings
from app.config import settings as default_settings
from app.db import initialize_database
from app.errors import ClientRequestError, UpstreamServiceError

logger = logging.getLogger(__name__)


def create_app(settings: Settings = default_settings) -> FastAPI:
    logging.basicConfig(level=getattr(logging, settings.log_level.upper(), logging.INFO))

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        initialize_database(settings.database_path)
        logger.info(
            "proxy.startup",
            extra={
                "app_name": settings.app_name,
                "database_path": str(settings.database_path),
                "ollama_base_url": settings.ollama_base_url,
                "max_request_body_bytes": settings.max_request_body_bytes,
            },
        )
        yield

    app = FastAPI(title=settings.app_name, lifespan=lifespan)
    app.state.settings = settings
    app.include_router(api_router)

    @app.exception_handler(UpstreamServiceError)
    async def upstream_error_handler(_: Request, exc: UpstreamServiceError) -> JSONResponse:
        return JSONResponse(
            status_code=502,
            content={"error": {"message": str(exc), "type": "upstream_error"}},
        )

    @app.exception_handler(ClientRequestError)
    async def client_request_error_handler(_: Request, exc: ClientRequestError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": {"message": str(exc), "type": exc.error_type}},
        )

    return app


app = create_app()
