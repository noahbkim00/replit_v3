from fastapi import FastAPI

from app.api.router import api_router
from app.core.config import Settings, get_settings
from app.middleware.request_id import RequestIDMiddleware
from app.middleware.request_size import RequestSizeLimitMiddleware


def create_app(settings: Settings | None = None) -> FastAPI:
    resolved_settings = settings or get_settings()

    app = FastAPI(
        title="FastAPI Ollama Proxy",
        version="0.1.0",
    )
    app.state.settings = resolved_settings

    app.add_middleware(RequestIDMiddleware)
    app.add_middleware(
        RequestSizeLimitMiddleware,
        max_body_size=resolved_settings.max_request_body_bytes,
    )
    app.include_router(api_router)

    return app


app = create_app()
