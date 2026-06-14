import httpx
import pytest
from httpx import ASGITransport, AsyncClient

from app.clients.ollama import OllamaClient
from app.core.config import Settings
from app.main import create_app

MODELS_RESPONSE = {
    "object": "list",
    "data": [
        {
            "id": "llama3.2:1b",
            "object": "model",
            "created": 1_700_000_000,
            "owned_by": "library",
        },
        {
            "id": "moondream:latest",
            "object": "model",
            "created": 1_700_000_001,
            "owned_by": "library",
        },
    ],
}


def _create_test_app(transport: httpx.AsyncBaseTransport):
    upstream_http_client = httpx.AsyncClient(
        transport=transport,
        base_url="http://ollama.test/v1/",
    )
    ollama_client = OllamaClient(
        base_url="http://ollama.test/v1",
        http_client=upstream_http_client,
    )
    settings = Settings(ollama_base_url="http://ollama.test/v1")

    return create_app(settings=settings, ollama_client=ollama_client)


@pytest.mark.anyio
@pytest.mark.parametrize("path", ["/v1/models", "/models"])
async def test_models_routes_pass_through_ollama_models(path: str) -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        assert str(request.url) == "http://ollama.test/v1/models"
        return httpx.Response(200, json=MODELS_RESPONSE)

    app = _create_test_app(httpx.MockTransport(handler))

    async with app.router.lifespan_context(app):
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://testserver",
        ) as client:
            response = await client.get(path)

    assert response.status_code == 200
    assert response.json() == MODELS_RESPONSE


@pytest.mark.anyio
async def test_models_route_maps_unavailable_ollama_to_502() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("could not connect", request=request)

    app = _create_test_app(httpx.MockTransport(handler))

    async with app.router.lifespan_context(app):
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://testserver",
        ) as client:
            response = await client.get("/v1/models")

    assert response.status_code == 502
    assert response.json() == {
        "error": {
            "message": "Ollama is unavailable",
            "type": "upstream_error",
            "code": "ollama_unavailable",
        }
    }


@pytest.mark.anyio
async def test_models_route_maps_ollama_timeout_to_504() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timed out", request=request)

    app = _create_test_app(httpx.MockTransport(handler))

    async with app.router.lifespan_context(app):
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://testserver",
        ) as client:
            response = await client.get("/models")

    assert response.status_code == 504
    assert response.json() == {
        "error": {
            "message": "Ollama request timed out",
            "type": "upstream_error",
            "code": "ollama_timeout",
        }
    }
