from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.router import api_router
from app.config import Settings
from app.config import settings as default_settings
from app.db import initialize_database


def create_app(settings: Settings = default_settings) -> FastAPI:
    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        initialize_database(settings.database_path)
        yield

    app = FastAPI(title=settings.app_name, lifespan=lifespan)
    app.include_router(api_router)
    return app


app = create_app()

