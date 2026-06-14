import argparse
import asyncio
import json
import time
import uuid
from collections.abc import AsyncIterator
from typing import Any

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse

DEFAULT_MODELS = ("llama3.2", "llama3.2:1b", "moondream")


def create_app(
    *,
    models: tuple[str, ...] = DEFAULT_MODELS,
    latency_ms: float = 0.0,
    prompt_tokens: int = 8,
    completion_tokens: int = 4,
) -> FastAPI:
    app = FastAPI(title="mock-ollama")
    app.state.models = models
    app.state.latency_ms = latency_ms
    app.state.prompt_tokens = prompt_tokens
    app.state.completion_tokens = completion_tokens

    @app.get("/models")
    @app.get("/v1/models")
    async def list_models() -> dict[str, Any]:
        return {
            "object": "list",
            "data": [
                {
                    "id": model,
                    "object": "model",
                    "created": 0,
                    "owned_by": "mock-ollama",
                }
                for model in app.state.models
            ],
        }

    @app.post("/chat/completions")
    @app.post("/v1/chat/completions")
    async def create_chat_completion(request: Request):
        payload = await request.json()
        if app.state.latency_ms > 0:
            await asyncio.sleep(app.state.latency_ms / 1000)

        usage = _usage(
            prompt_tokens=app.state.prompt_tokens,
            completion_tokens=app.state.completion_tokens,
        )
        if payload.get("stream") is True:
            return StreamingResponse(
                _stream_response(payload=payload, usage=usage),
                media_type="text/event-stream",
            )

        return _chat_response(payload=payload, usage=usage)

    return app


def _usage(prompt_tokens: int, completion_tokens: int) -> dict[str, int]:
    return {
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": prompt_tokens + completion_tokens,
    }


def _chat_response(payload: dict[str, Any], usage: dict[str, int]) -> dict[str, Any]:
    return {
        "id": f"chatcmpl-mock-{uuid.uuid4().hex}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": payload.get("model", "llama3.2:1b"),
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": "mock response"},
                "finish_reason": "stop",
            }
        ],
        "usage": usage,
    }


async def _stream_response(
    *, payload: dict[str, Any], usage: dict[str, int]
) -> AsyncIterator[bytes]:
    model = payload.get("model", "llama3.2:1b")
    chunk = {
        "id": f"chatcmpl-mock-{uuid.uuid4().hex}",
        "object": "chat.completion.chunk",
        "created": int(time.time()),
        "model": model,
        "choices": [
            {
                "index": 0,
                "delta": {"role": "assistant", "content": "mock response"},
                "finish_reason": None,
            }
        ],
        "usage": None,
    }
    final_chunk = {
        "id": chunk["id"],
        "object": "chat.completion.chunk",
        "created": int(time.time()),
        "model": model,
        "choices": [
            {
                "index": 0,
                "delta": {},
                "finish_reason": "stop",
            }
        ],
        "usage": usage,
    }
    yield f"data: {json.dumps(chunk)}\n\n".encode()
    yield f"data: {json.dumps(final_chunk)}\n\n".encode()
    yield b"data: [DONE]\n\n"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run a fast local mock of Ollama's OpenAI-compatible endpoints."
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=11435)
    parser.add_argument("--latency-ms", type=float, default=0.0)
    parser.add_argument("--prompt-tokens", type=int, default=8)
    parser.add_argument("--completion-tokens", type=int, default=4)
    parser.add_argument(
        "--models",
        default=",".join(DEFAULT_MODELS),
        help="Comma-separated model IDs to expose from /v1/models.",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    models = tuple(model.strip() for model in args.models.split(",") if model.strip())
    app = create_app(
        models=models or DEFAULT_MODELS,
        latency_ms=args.latency_ms,
        prompt_tokens=max(args.prompt_tokens, 0),
        completion_tokens=max(args.completion_tokens, 0),
    )
    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
