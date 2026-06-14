from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.api.router import api_router
from app.config import Settings
from app.config import settings as default_settings
from app.db import initialize_database
from app.errors import UpstreamServiceError


def create_app(settings: Settings = default_settings) -> FastAPI:
    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        initialize_database(settings.database_path)
        yield

    app = FastAPI(title=settings.app_name, lifespan=lifespan)
    app.state.settings = settings
    app.include_router(api_router)

    @app.exception_handler(UpstreamServiceError)
    async def upstream_error_handler(
        _: Request, exc: UpstreamServiceError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=502,
            content={"error": {"message": str(exc), "type": "upstream_error"}},
        )

    return app


app = create_app()
