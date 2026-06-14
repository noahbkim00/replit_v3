# Testing and Demos

Set up the local environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
```

If the virtualenv is not active on this machine, use `python3` in place of
`python`.

## Automated Unit Tests

The unit tests do not require real Ollama. They exercise the real FastAPI app,
auth dependencies, SQLite repositories against temporary databases, services,
usage tracking, and limit reservation code. Tests stub only the `OllamaClient`
boundary.

Run the full suite and lint:

```bash
python -m pytest -q
python -m ruff check .
```

Useful focused checks:

```bash
python -m pytest tests/test_app_lifecycle_and_database.py -q
python -m pytest tests/test_auth_models_and_seed_data.py -q
python -m pytest tests/test_chat_completions_usage.py -q
python -m pytest tests/test_streaming_vision_and_request_validation.py -q
python -m pytest tests/test_usage_and_limits_api.py -q
python -m pytest tests/test_atomic_limit_reservations_and_client_lifecycle.py -q
python -m pytest tests/test_ollama_concurrency_controls.py -q
python -m pytest tests/test_demo_load_test_metrics.py -q
```

Format before final review:

```bash
python -m ruff format .
python -m ruff check .
```

## Real Ollama Demo Setup

The demo scripts are the take-home proof path. They require the proxy, local
Ollama, and pulled models; they do not use `scripts/mock_ollama.py`.

Start Ollama and pull models:

```bash
ollama serve
ollama pull llama3.2:1b
ollama pull moondream
```

Use a fresh SQLite database for deterministic usage and limit output:

```bash
rm -f /tmp/replit-v3-demo.sqlite3 /tmp/replit-v3-demo.sqlite3-*
DATABASE_PATH=/tmp/replit-v3-demo.sqlite3 python scripts/seed_dev_data.py
DATABASE_PATH=/tmp/replit-v3-demo.sqlite3 \
OLLAMA_TIMEOUT_SECONDS=90 \
uvicorn app.main:app --host 127.0.0.1 --port 8000 --no-access-log
```

Seeded tokens:

- `dev-token-user-a`
- `dev-token-user-b`
- `dev-token-admin`

Expected environment defaults:

- Proxy: `http://127.0.0.1:8000`
- Ollama OpenAI-compatible URL: `http://localhost:11434/v1`
- Models: `llama3.2:1b`, `moondream`
- Ollama may list untagged models with `:latest`; the proxy model list treats
  `model` and `model:latest` as equivalent for allowlisted models.

## Demo Commands

Run in another terminal while the proxy is up:

```bash
python scripts/demo_standard.py --proxy-url http://127.0.0.1:8000
python scripts/demo_streaming.py --proxy-url http://127.0.0.1:8000
python scripts/demo_usage.py --proxy-url http://127.0.0.1:8000
python scripts/demo_limits.py --proxy-url http://127.0.0.1:8000
python scripts/demo_concurrency.py --proxy-url http://127.0.0.1:8000
python scripts/demo_load_test.py --proxy-url http://127.0.0.1:8000 \
  --requests 300 --concurrency 50 --limited-allowed 150
```

The standard and streaming demos use the real `openai` package for text and
vision chat completions. The usage, limits, concurrency, and load demos use the
real `openai` package for chat traffic and `httpx` for proxy usage/admin APIs.

The load demo uses `user_a` for the no-limit scenario and `user_b` for the
limited scenario so the no-limit traffic does not consume the limited user's
rolling request-per-minute window.

## Expected Failure Guidance

- Proxy unavailable: start Uvicorn with the fresh demo DB command above.
- `upstream_error` / Ollama unavailable: run `ollama serve`.
- Missing models: run `ollama pull llama3.2:1b` and `ollama pull moondream`.
- `demo_limits.py` first call is rate-limited: use a fresh demo database or wait
  60 seconds, because request-per-minute limits count recent successful and
  reserved usage rows.
- `demo_load_test.py` reports that the limited scenario needs a fresh window: use
  a fresh demo database or wait 60 seconds before rerunning it.
