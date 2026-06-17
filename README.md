# FastAPI Ollama Proxy

OpenAI-compatible FastAPI proxy for local Ollama with bearer-token auth,
per-user usage tracking, admin-configurable limits, streaming chat, and vision
requests.

## Setup

```bash
make setup
make ollama-pull
make start
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

## Common Make Commands

| Command | Description |
| --- | --- |
| `make install` | Create `.venv` and install the package with dev tools. |
| `make setup` | Install dependencies and seed development users/tokens/models. |
| `make start` | Start the proxy on `127.0.0.1:8000`. |
| `make test` | Run unit tests; real Ollama is not required. |
| `make check` | Run Ruff and unit tests. |
| `make demo DEMO=standard` | Run one selected demo. |
| `make demos` | Run non-load real-Ollama demos. |
| `make demo-load` | Run the heavier load demo separately. |

Real demo targets require Ollama running with the required models pulled, plus
the proxy running with seeded data:

```bash
ollama serve
make ollama-pull
make start
```

## Tests

Unit tests do not require real Ollama; they stub only the Ollama client boundary.

```bash
make test
make check
```

See `testing.md` for focused commands and real-Ollama demo workflows.

## Without Make

The Makefile is a thin wrapper around the project tooling. Equivalent manual
setup commands are:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
python scripts/seed_dev_data.py
uvicorn app.main:app --host 127.0.0.1 --port 8000
```
