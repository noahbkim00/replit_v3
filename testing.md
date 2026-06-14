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
Admin token: dev-token-admin
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

image_response = httpx.get(
    "https://picsum.photos/seed/replit-v3/320/240",
    follow_redirects=True,
)
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

## Phase 4 Checks

Seed the development users, tokens, model allowlist, and admin token:

```bash
python scripts/seed_dev_data.py
```

Expected output includes:

```text
User A token: dev-token-user-a
User B token: dev-token-user-b
Admin token: dev-token-admin
```

Run the automated Phase 4 checks, which mock the upstream Ollama path and verify
that limit-rejected requests do not call the upstream client:

```bash
python -m pytest tests/test_phase4.py
python -m pytest
python -m ruff check .
```

For local usage API and admin limit checks, start Ollama, make sure `llama3.2:1b`
is available, seed the proxy database, and run the proxy:

```bash
ollama serve
ollama pull llama3.2:1b
python scripts/seed_dev_data.py
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

In another terminal, create one successful User A request and one successful User B
request:

```bash
curl -sS http://localhost:8000/v1/chat/completions \
  -H "Authorization: Bearer dev-token-user-a" \
  -H "Content-Type: application/json" \
  -d '{"model":"llama3.2:1b","messages":[{"role":"user","content":"Say A."}],"max_tokens":16}' >/dev/null

curl -sS http://localhost:8000/v1/chat/completions \
  -H "Authorization: Bearer dev-token-user-b" \
  -H "Content-Type: application/json" \
  -d '{"model":"llama3.2:1b","messages":[{"role":"user","content":"Say B."}],"max_tokens":16}' >/dev/null
```

User A usage summary:

```bash
curl -sS http://localhost:8000/usage \
  -H "Authorization: Bearer dev-token-user-a"
```

Expected response shape:

```json
{"user_id":"user_a","aggregate":{"prompt_tokens":1,"completion_tokens":1,"total_tokens":2,"request_count":1},"models":[{"model":"llama3.2:1b","prompt_tokens":1,"completion_tokens":1,"total_tokens":2,"request_count":1}]}
```

Token counts depend on local Ollama, but `user_id` should be `user_a` and all
returned totals should belong only to User A.

User A usage events:

```bash
curl -sS http://localhost:8000/usage/events \
  -H "Authorization: Bearer dev-token-user-a"
```

Expected response shape:

```json
{"user_id":"user_a","events":[{"id":1,"user_id":"user_a","model":"llama3.2:1b","prompt_tokens":1,"completion_tokens":1,"total_tokens":2,"latency_ms":10.0,"status":"success","timestamp":"2026-06-13 00:00:00"}]}
```

Proof that User A only sees User A usage:

```bash
curl -sS http://localhost:8000/usage/events \
  -H "Authorization: Bearer dev-token-user-a" \
  | python -m json.tool

curl -sS http://localhost:8000/usage/events \
  -H "Authorization: Bearer dev-token-user-b" \
  | python -m json.tool
```

The first response should have `user_id` set to `user_a` and event rows with
`"user_id": "user_a"`. The second response should have `user_id` set to `user_b`
and event rows with `"user_id": "user_b"`. There is no user-scoped endpoint that
accepts another user's ID.

Admin set/get limits:

```bash
curl -sS -X PUT http://localhost:8000/admin/users/user_a/limits \
  -H "Authorization: Bearer dev-token-admin" \
  -H "Content-Type: application/json" \
  -d '{"requests_per_minute":2,"daily_tokens":1000,"total_tokens":5000}'

curl -sS http://localhost:8000/admin/users/user_a/limits \
  -H "Authorization: Bearer dev-token-admin"
```

Expected response:

```json
{"user_id":"user_a","requests_per_minute":2,"daily_tokens":1000,"total_tokens":5000}
```

Non-admin users cannot use admin routes:

```bash
curl -i -X PUT http://localhost:8000/admin/users/user_a/limits \
  -H "Authorization: Bearer dev-token-user-a" \
  -H "Content-Type: application/json" \
  -d '{"requests_per_minute":2}'
```

Expected response is `HTTP/1.1 403 Forbidden`.

Admin usage view for a user:

```bash
curl -sS http://localhost:8000/admin/users/user_a/usage \
  -H "Authorization: Bearer dev-token-admin"
```

Expected response shape matches `GET /usage`, but for the `user_id` in the admin
path.

Request-per-minute rejection example:

```bash
curl -sS -X PUT http://localhost:8000/admin/users/user_a/limits \
  -H "Authorization: Bearer dev-token-admin" \
  -H "Content-Type: application/json" \
  -d '{"requests_per_minute":1,"daily_tokens":null,"total_tokens":null}'

curl -i http://localhost:8000/v1/chat/completions \
  -H "Authorization: Bearer dev-token-user-a" \
  -H "Content-Type: application/json" \
  -d '{"model":"llama3.2:1b","messages":[{"role":"user","content":"first"}],"max_tokens":8}'

curl -i http://localhost:8000/v1/chat/completions \
  -H "Authorization: Bearer dev-token-user-a" \
  -H "Content-Type: application/json" \
  -d '{"model":"llama3.2:1b","messages":[{"role":"user","content":"second"}],"max_tokens":8}'
```

The second request should return `HTTP/1.1 429 Too Many Requests` with:

```json
{"error":{"message":"Request rate limit exceeded","type":"rate_limit_exceeded"}}
```

`429` limit rejections happen before the proxy calls Ollama. They do not create
successful usage events or update `usage_totals`.

Daily-token or total-token rejection example:

```bash
curl -sS -X PUT http://localhost:8000/admin/users/user_a/limits \
  -H "Authorization: Bearer dev-token-admin" \
  -H "Content-Type: application/json" \
  -d '{"requests_per_minute":null,"daily_tokens":12,"total_tokens":12}'

curl -i http://localhost:8000/v1/chat/completions \
  -H "Authorization: Bearer dev-token-user-a" \
  -H "Content-Type: application/json" \
  -d '{"model":"llama3.2:1b","messages":[{"role":"user","content":"try token cap"}],"max_tokens":64}'
```

If User A already has enough successful usage that `existing_tokens + max_tokens`
exceeds either configured cap, the response should be `429`:

```json
{"error":{"message":"Token limit exceeded for daily_tokens","type":"rate_limit_exceeded"}}
```

The proxy uses `max_tokens` as the token projection for this preflight check, and
the rejected request does not reach Ollama or create a successful usage event.

## Phase 5 Checks

Run the automated Phase 5 checks:

```bash
python -m pytest tests/test_phase5.py
python -m pytest
python -m ruff check .
```

### Proxy Overhead Load Test With Mock Ollama

Use a temporary database for repeatable load-test runs:

```bash
DATABASE_PATH=/tmp/replit-v3-load.sqlite3 python scripts/seed_dev_data.py
```

Start the mock Ollama server in one terminal. The mock serves OpenAI-compatible
model and chat endpoints without real generation latency:

```bash
python -m uvicorn scripts.mock_ollama:create_app \
  --factory \
  --host 127.0.0.1 \
  --port 11435 \
  --no-access-log
```

Start the proxy in another terminal and point it at the mock. Multiple Uvicorn
workers are useful for measuring proxy overhead rather than single-process server
serialization:

```bash
DATABASE_PATH=/tmp/replit-v3-load.sqlite3 \
OLLAMA_BASE_URL=http://127.0.0.1:11435/v1 \
uvicorn app.main:app \
  --host 127.0.0.1 \
  --port 8000 \
  --workers 4 \
  --no-access-log
```

Run the proxy overhead load test:

```bash
python scripts/load_test.py \
  --mode proxy-overhead \
  --proxy-url http://127.0.0.1:8000 \
  --requests 400 \
  --concurrency 200 \
  --clear-limits
```

The JSON report includes:

- `requests_per_second`: completed requests divided by measured elapsed time.
- `p50_latency_ms`, `p95_latency_ms`, `p99_latency_ms`: observed client-side
  request latency percentiles.
- `error_rate`: non-2xx responses plus client/network errors divided by total
  requests.
- `limit_rejection_rate`: `429` or `rate_limit_exceeded` responses divided by
  total requests.
- `usage_event_count`: the delta in `GET /usage/events` count before and after
  the run.
- `usage_comparison.usage_events_match_successes`: should be `true` when each
  successful request created exactly one usage event.
- `usage_comparison.usage_totals_match_successes`: should be `true` when
  `GET /usage` request-count totals increased by the successful request count.

For the proxy overhead test, expect `error_rate` and `limit_rejection_rate` to be
`0.0`, and expect `usage_event_count` to equal `successful_requests`. On the
verification machine, this workflow produced 400 successful requests, 400 usage
events, and 229 RPS.

You can also inspect persisted usage directly:

```bash
sqlite3 /tmp/replit-v3-load.sqlite3 \
  "SELECT COUNT(*) FROM usage_events WHERE user_id = 'user_a' AND status = 'success';"

sqlite3 /tmp/replit-v3-load.sqlite3 \
  "SELECT request_count, total_tokens FROM usage_totals WHERE user_id = 'user_a' AND model = 'llama3.2:1b';"
```

### Limit Rejection Behavior Under Concurrency

After the successful overhead run above, set a low request limit and run concurrent
requests again:

```bash
python scripts/load_test.py \
  --mode proxy-overhead \
  --proxy-url http://127.0.0.1:8000 \
  --requests 50 \
  --concurrency 25 \
  --set-request-limit 1
```

Because the same user already has recent successful usage, the run should return
`429` responses. Expected interpretation:

- `limit_rejections` should be greater than `0`; if the prior overhead run was
  recent, it should equal `total_requests`.
- `limit_rejection_rate` should be greater than `0.0`.
- `usage_event_count` should be `0` when all requests are rejected.
- `usage_comparison.usage_events_match_successes` should remain `true`.

Clear limits before returning to normal manual testing:

```bash
python scripts/load_test.py \
  --proxy-url http://127.0.0.1:8000 \
  --requests 0 \
  --concurrency 1 \
  --clear-limits
```

### Real Ollama Load Test

The real Ollama test uses the same proxy path but points the proxy at local Ollama
instead of `scripts/mock_ollama.py`. Report these results separately because token
generation speed is hardware-bound.

Make sure Ollama is running and the small model is available:

```bash
ollama serve
ollama pull llama3.2:1b
```

Use a separate temporary database:

```bash
DATABASE_PATH=/tmp/replit-v3-real-load.sqlite3 python scripts/seed_dev_data.py
```

Start the proxy with the default Ollama base URL:

```bash
DATABASE_PATH=/tmp/replit-v3-real-load.sqlite3 \
uvicorn app.main:app \
  --host 127.0.0.1 \
  --port 8000 \
  --no-access-log
```

Run a smaller hardware-bound test:

```bash
python scripts/load_test.py \
  --mode real-ollama \
  --proxy-url http://127.0.0.1:8000 \
  --model llama3.2:1b \
  --requests 10 \
  --concurrency 2 \
  --max-tokens 16 \
  --clear-limits \
  --timeout-seconds 60
```

Interpret usage metrics the same way as the mock test: successful real-Ollama
requests should create matching usage events and usage-total request-count deltas.
RPS and latency are expected to be much lower than the mock proxy-overhead test.
