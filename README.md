# FastAPI Ollama Proxy

OpenAI-compatible FastAPI proxy for local Ollama with bearer-token auth,
per-user usage tracking, admin-configurable limits, streaming chat, and vision
requests.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
python scripts/seed_dev_data.py
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Health check:

```bash
curl http://localhost:8000/healthz
```

Seeded development tokens:

- `dev-token-user-a`
- `dev-token-user-b`
- `dev-token-admin`

## Ollama

Run local Ollama and pull the required models:

```bash
ollama serve
ollama pull llama3.2:1b
ollama pull moondream
```

The proxy defaults to `OLLAMA_BASE_URL=http://localhost:11434/v1`.

## Tests

Unit tests do not require real Ollama; they stub only the Ollama client boundary.

```bash
python -m pytest -q
python -m ruff check .
```

See `testing.md` for focused commands and real-Ollama demo workflows.
