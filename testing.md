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

## Phase 2 Checks

Seed the development users, tokens, and model allowlist:

```bash
python scripts/seed_dev_data.py
```

Run the automated Phase 2 checks, which mock the upstream Ollama path:

```bash
python -m pytest tests/test_phase2.py
python -m pytest
python -m ruff check .
```

For a local non-streaming chat check with the OpenAI Python client, start Ollama,
make sure `llama3.2:1b` is available, seed the proxy database, and run the proxy:

```bash
ollama serve
ollama pull llama3.2:1b
python scripts/seed_dev_data.py
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

In another terminal:

```bash
python - <<'PY'
from openai import OpenAI

client = OpenAI(
    base_url="http://localhost:8000/v1",
    api_key="dev-token-user-a",
)

response = client.chat.completions.create(
    model="llama3.2:1b",
    messages=[{"role": "user", "content": "What is 2+2?"}],
    max_tokens=32,
)

print(response.choices[0].message.content)
print(response.usage)
PY
```

The request should return a normal non-streaming chat completion. Confirm one usage
event and one per-user/per-model total were persisted:

```bash
sqlite3 data/proxy.sqlite3 \
  "SELECT user_id, model, prompt_tokens, completion_tokens, total_tokens, status, timestamp FROM usage_events ORDER BY id DESC LIMIT 1;"

sqlite3 data/proxy.sqlite3 \
  "SELECT user_id, model, prompt_tokens, completion_tokens, total_tokens, request_count FROM usage_totals ORDER BY user_id, model;"
```

Expected persistence behavior:

- The latest `usage_events` row should be for `user_a`, `llama3.2:1b`, with
  `status` set to `success`.
- `usage_totals` should include an updated `user_a` / `llama3.2:1b` row.

Verify `stream=true` is rejected for now and is not billed:

```bash
before=$(sqlite3 data/proxy.sqlite3 "SELECT COUNT(*) FROM usage_events;")
curl -i http://localhost:8000/v1/chat/completions \
  -H "Authorization: Bearer dev-token-user-a" \
  -H "Content-Type: application/json" \
  -d '{"model":"llama3.2:1b","messages":[{"role":"user","content":"hello"}],"stream":true}'
after=$(sqlite3 data/proxy.sqlite3 "SELECT COUNT(*) FROM usage_events;")
printf "before=%s after=%s\n" "$before" "$after"
```

Expected response:

```json
{"error":{"message":"stream=true is not supported yet","type":"invalid_request_error"}}
```

`before` and `after` should match.

Verify invalid auth is not billed:

```bash
before=$(sqlite3 data/proxy.sqlite3 "SELECT COUNT(*) FROM usage_events;")
curl -i http://localhost:8000/v1/chat/completions \
  -H "Authorization: Bearer not-a-token" \
  -H "Content-Type: application/json" \
  -d '{"model":"llama3.2:1b","messages":[{"role":"user","content":"hello"}]}'
after=$(sqlite3 data/proxy.sqlite3 "SELECT COUNT(*) FROM usage_events;")
printf "before=%s after=%s\n" "$before" "$after"
```

Expected response is `HTTP/1.1 401 Unauthorized`, and `before` and `after` should
match.

To check the upstream failure behavior without stopping any existing Ollama process,
run the proxy against an unused local port:

```bash
OLLAMA_BASE_URL=http://127.0.0.1:9/v1 uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Then in another terminal:

```bash
before=$(sqlite3 data/proxy.sqlite3 "SELECT COUNT(*) FROM usage_events;")
curl -i http://localhost:8000/v1/chat/completions \
  -H "Authorization: Bearer dev-token-user-a" \
  -H "Content-Type: application/json" \
  -d '{"model":"llama3.2:1b","messages":[{"role":"user","content":"hello"}]}'
after=$(sqlite3 data/proxy.sqlite3 "SELECT COUNT(*) FROM usage_events;")
printf "before=%s after=%s\n" "$before" "$after"
```

Expected response:

```json
{"error":{"message":"Ollama is unavailable","type":"upstream_error"}}
```

`before` and `after` should match because failed upstream requests do not invent
token usage.
