# Testing

Set up the local environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
```

## Phase 0 Checks

```bash
python -m pytest tests/test_phase0.py
python -m ruff check .
```

Run the server and verify the health endpoint:

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000
curl http://localhost:8000/healthz
```

Expected response:

```json
{"status":"ok"}
```

The server initializes SQLite at `data/proxy.sqlite3` by default. To use a different
location for local testing:

```bash
DATABASE_PATH=/tmp/replit-v3-proxy.sqlite3 uvicorn app.main:app --host 0.0.0.0 --port 8000
```

## Phase 1 Checks

Seed the development users, tokens, and model allowlist:

```bash
python scripts/seed_dev_data.py
```

Expected output includes:

```text
User A token: dev-token-user-a
User B token: dev-token-user-b
```

Run the automated Phase 1 checks:

```bash
python -m pytest tests/test_phase1.py
python -m pytest
python -m ruff check .
```

For a local authenticated models check, start Ollama and make at least one allowlisted
model available:

```bash
ollama serve
ollama pull llama3.2
ollama pull llama3.2:1b
ollama pull moondream
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

In another terminal, verify auth failures:

```bash
curl -i http://localhost:8000/v1/models
curl -i -H "Authorization: Bearer not-a-token" http://localhost:8000/v1/models
```

Both commands should return `HTTP/1.1 401 Unauthorized`.

Verify authenticated success through both model routes:

```bash
curl -sS -H "Authorization: Bearer dev-token-user-a" http://localhost:8000/v1/models
curl -sS -H "Authorization: Bearer dev-token-user-a" http://localhost:8000/models
```

Expected response shape:

```json
{"object":"list","data":[{"id":"llama3.2","object":"model"}]}
```

The exact `data` entries depend on which allowlisted models are installed in local
Ollama. Non-allowlisted Ollama models are filtered out by the proxy.

To check the clean upstream error path without stopping any existing Ollama process,
run the proxy against an unused local port:

```bash
OLLAMA_BASE_URL=http://127.0.0.1:9/v1 uvicorn app.main:app --host 0.0.0.0 --port 8000
curl -i -H "Authorization: Bearer dev-token-user-a" http://localhost:8000/v1/models
```

Expected response:

```json
{"error":{"message":"Ollama is unavailable","type":"upstream_error"}}
```
