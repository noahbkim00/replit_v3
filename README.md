# FastAPI Ollama Proxy

Phase 0 establishes the runnable FastAPI skeleton for the Ollama proxy take-home.

## Local Setup

Install dependencies and run the test suite:

```bash
uv run pytest
uv run ruff check .
```

Run the API locally:

```bash
uv run uvicorn app.main:app --port 8000
```

Verify the smoke endpoint:

```bash
curl http://localhost:8000/healthz
```

Expected response:

```json
{"status":"ok"}
```

## Ollama Prerequisites

Later proxy phases require local Ollama models:

```bash
ollama pull llama3.2
ollama pull moondream
```
