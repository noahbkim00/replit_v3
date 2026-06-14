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

## Phase 3 Checks

Seed the development users, tokens, and model allowlist:

```bash
python scripts/seed_dev_data.py
```

Run the automated Phase 3 checks, which mock the upstream Ollama path:

```bash
python -m pytest tests/test_phase3.py
python -m pytest
python -m ruff check .
```

For a local streaming check with the OpenAI Python client, start Ollama, make sure
`llama3.2:1b` is available, seed the proxy database, and run the proxy:

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

stream = client.chat.completions.create(
    model="llama3.2:1b",
    messages=[{"role": "user", "content": "Count from one to five."}],
    max_tokens=64,
    stream=True,
    stream_options={"include_usage": True},
)

for chunk in stream:
    if chunk.choices:
        print(chunk.choices[0].delta.content or "", end="", flush=True)
    if chunk.usage:
        print(f"\nusage={chunk.usage}")
print()
PY
```

The response text should print incrementally. Confirm exactly one persisted usage
event for the streaming request:

```bash
sqlite3 data/proxy.sqlite3 \
  "SELECT user_id, model, prompt_tokens, completion_tokens, total_tokens, status, timestamp FROM usage_events ORDER BY id DESC LIMIT 1;"

sqlite3 data/proxy.sqlite3 \
  "SELECT user_id, model, prompt_tokens, completion_tokens, total_tokens, request_count FROM usage_totals WHERE user_id = 'user_a' AND model = 'llama3.2:1b';"
```

Expected persistence behavior:

- The latest `usage_events` row should be for `user_a`, `llama3.2:1b`, with
  `status` set to `success`.
- `usage_totals.request_count` for `user_a` / `llama3.2:1b` should increase by one.
- If the upstream stream fails before Ollama sends final usage, the proxy does not
  create a synthetic token-usage event.

You can also inspect the SSE stream with `curl`:

```bash
curl -N http://localhost:8000/v1/chat/completions \
  -H "Authorization: Bearer dev-token-user-a" \
  -H "Content-Type: application/json" \
  -d '{"model":"llama3.2:1b","messages":[{"role":"user","content":"Say hello slowly."}],"stream":true}'
```

For a local vision check, start Ollama, make sure `moondream` is available, seed the
proxy database, and run the proxy:

```bash
ollama serve
ollama pull moondream
python scripts/seed_dev_data.py
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

In another terminal, download Lorem Picsum in the client script, encode it as a
base64 data URL, and send that data URL to the proxy:

```bash
python - <<'PY'
import base64

import httpx
from openai import OpenAI

image_response = httpx.get("https://picsum.photos/seed/replit-v3/320/240")
image_response.raise_for_status()
image_data_url = (
    "data:image/jpeg;base64,"
    + base64.b64encode(image_response.content).decode("ascii")
)

client = OpenAI(
    base_url="http://localhost:8000/v1",
    api_key="dev-token-user-a",
)

response = client.chat.completions.create(
    model="moondream",
    messages=[
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "Describe this image in one sentence."},
                {"type": "image_url", "image_url": {"url": image_data_url}},
            ],
        }
    ],
    max_tokens=64,
)

print(response.choices[0].message.content)
print(response.usage)
PY
```

The proxy accepts base64 data URLs and forwards the OpenAI-style image content to
Ollama. It does not download remote image URLs itself; remote image URLs sent in
the request body are rejected with `400`.

Confirm vision usage when Ollama returns usage:

```bash
sqlite3 data/proxy.sqlite3 \
  "SELECT user_id, model, prompt_tokens, completion_tokens, total_tokens, status, timestamp FROM usage_events ORDER BY id DESC LIMIT 1;"
```

Expected persistence behavior:

- The latest `usage_events` row should be for `user_a`, `moondream`, with
  `status` set to `success`.
- Token counts depend on the local Ollama/moondream response.

If local Ollama is not running, the proxy returns a clean upstream error:

```json
{"error":{"message":"Ollama is unavailable","type":"upstream_error"}}
```

If `moondream` is not pulled locally, Ollama may return an upstream model error
through the proxy. Pull it with `ollama pull moondream` and retry the vision demo.
