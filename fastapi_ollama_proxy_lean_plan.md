# FastAPI Ollama Proxy — Lean Phase Plan

## Goal

Build the required take-home assignment with a clean separation of concerns, but without an over-engineered implementation plan.

The project should support:

- OpenAI-compatible chat completions through Ollama
- Streaming chat completions
- Vision requests with `moondream`
- Per-user usage tracking
- Admin-configurable usage limits
- Load testing that demonstrates proxy-level concurrency

Out of scope:

- Bonus features
- Legacy `/v1/completions`
- Admin UI
- Redis/Postgres unless needed later
- Complex domain layering

---

## Architecture

Keep the code clean, but small.

```text
app/
  main.py
  config.py
  db.py
  errors.py

  api/
    deps.py
    routes/
      health.py
      models.py
      chat.py
      usage.py
      admin.py

  clients/
    ollama.py

  services/
    auth.py
    models.py
    chat_proxy.py
    usage.py
    limits.py

  repositories/
    users.py
    usage.py
    limits.py

scripts/
  seed_dev_data.py
  demo_chat.py
  demo_streaming.py
  demo_vision.py
  mock_ollama.py
  load_test.py

tests/
  test_auth.py
  test_chat.py
  test_streaming.py
  test_usage.py
  test_limits.py

README.md
pyproject.toml
.env.example
```

## Separation of Concerns

### Routes

Routes handle HTTP only:

- parse request
- use dependencies
- call services
- return response

Routes should not contain database queries, Ollama calls, usage calculations, or limit logic.

### Services

Services own business flow:

- authenticate users
- validate models
- check limits
- proxy chat requests
- extract and record usage
- enforce admin settings

### Repositories

Repositories own SQLite access.

No route should talk directly to SQLite.

### Clients

`clients/ollama.py` is the only module that knows how to call Ollama.

---

## Phase 0 — Project Skeleton

### Objective

Create the app structure and prove the server starts.

### Build

- Create the file structure.
- Add FastAPI, Uvicorn, HTTPX, Pydantic, OpenAI client, Pytest, and Ruff.
- Add config loading.
- Add SQLite initialization.
- Add `GET /healthz`.

### Validate

- Server starts on port `8000`.
- `GET /healthz` returns `{"status": "ok"}`.
- Tests and linting run.

### Done When

The empty app is runnable and follows the intended structure.

---

## Phase 1 — Auth, Models, and Ollama Connectivity

### Objective

Prove the proxy can identify users and talk to Ollama before implementing completions.

### Build

- Add SQLite tables:
  - `users`
  - `api_tokens`
  - `model_allowlist`
- Seed:
  - `user_a`
  - `user_b`
  - dev API tokens
- Add auth dependency.
- Add model allowlist:
  - `llama3.2`
  - `llama3.2:1b`
  - `moondream`
- Implement:
  - `GET /v1/models`
  - `GET /models`
- Forward models request to Ollama.

### Validate

- Valid token succeeds.
- Missing/invalid token returns `401`.
- Ollama unavailable returns a clean upstream error.
- `/v1/models` works through the proxy.

### Done When

Authenticated model requests can reach Ollama through the proxy.

---

## Phase 2 — Non-Streaming Chat + Usage Tracking

### Objective

Build the first complete billable request path.

```text
user request
  → auth
  → model check
  → limit preflight placeholder
  → Ollama chat completion
  → usage recorded
  → response returned
```

### Build

- Implement:
  - `POST /v1/chat/completions`
  - `POST /chat/completions`
- Support non-streaming chat first.
- Temporarily reject `stream=true`.
- Forward request bodies mostly unchanged to Ollama.
- Extract `usage` from the response.
- Record usage in SQLite:
  - user
  - model
  - prompt tokens
  - completion tokens
  - total tokens
  - latency
  - status
  - timestamp
- Maintain simple per-user/per-model totals.

### Validate

- OpenAI Python client works with `base_url="http://localhost:8000/v1"`.
- A successful request creates one usage event.
- Usage totals update.
- Invalid auth is not billed.
- Failed upstream requests do not invent token usage.

### Done When

Non-streaming chat works and usage is persisted.

---

## Phase 3 — Streaming and Vision

### Objective

Complete the required model capabilities.

### Build

Add streaming support to the same chat endpoint:

- use `StreamingResponse`
- stream SSE chunks from Ollama
- force or merge `stream_options.include_usage=true`
- capture final usage when available
- write one usage event after stream completion

Add vision support through the same chat endpoint:

- allow `moondream`
- accept OpenAI-style image content
- support base64 data URLs
- do not download remote images in the proxy
- enforce a basic request body size limit

### Validate

- OpenAI Python client streaming works.
- Streaming chunks arrive incrementally.
- Streaming usage is recorded once.
- Vision demo sends a Lorem Picsum image as a base64 data URL.
- `moondream` responds to an image question.
- Vision usage is recorded.

### Done When

Text, streaming, and vision requests all work through `/v1/chat/completions`.

---

## Phase 4 — User Usage API and Admin Limits

### Objective

Expose usage to users and allow admins to enforce limits.

### Build

User endpoints:

```text
GET /usage
GET /usage/events
```

Admin endpoints:

```text
PUT /admin/users/{user_id}/limits
GET /admin/users/{user_id}/limits
GET /admin/users/{user_id}/usage
```

Support simple limit types:

- `requests_per_minute`
- `daily_tokens`
- `total_tokens`

Enforce limits before forwarding to Ollama:

- check request rate
- estimate token usage from `max_tokens`
- reject with `429` when projected usage exceeds limits
- record actual usage after successful completion

### Validate

- User A sees only User A usage.
- User B sees only User B usage.
- Admin can set a low request limit.
- User receives `429` after hitting the limit.
- Admin can set a low token cap.
- Requests that exceed limits do not reach Ollama.

### Done When

Users can view usage, and admins can prevent excessive usage.

---

## Phase 5 — Load Testing

### Objective

Demonstrate that the final proxy path handles concurrent users.

### Build

Add:

```text
scripts/mock_ollama.py
scripts/load_test.py
```

The load test should measure:

- requests per second
- p50 latency
- p95 latency
- p99 latency
- error rate
- limit rejection rate
- usage event count

Run two kinds of tests:

### Proxy Overhead Test

Use mock Ollama to prove the FastAPI proxy path handles hundreds of requests per second.

This should include:

- auth
- model validation
- limit checks
- usage recording

### Real Ollama Test

Use local `llama3.2:1b`.

Report separately because generation speed is hardware-bound.

### Validate

- Mock upstream test reaches hundreds of RPS.
- Real Ollama test is stable.
- Usage totals match successful requests.
- Limit behavior remains correct under concurrency.

### Done When

There is repeatable evidence that the final billing-aware proxy handles concurrent users.

---

## Phase 6 — README and Final Demo

### Objective

Make the project easy to run and defend.

### Build

README should include:

- setup
- model pulls
- seed command
- run command
- non-streaming demo
- streaming demo
- vision demo
- usage API examples
- admin limit examples
- load test command
- short design explanation

### Validate

Run from a clean checkout:

- health check works
- models endpoint works
- non-streaming chat works
- streaming chat works
- vision works
- usage API works
- admin limits work
- load test runs

### Done When

The project is ready to submit and discuss in an interview.

---

## Final Phase Order

```text
Phase 0 — Project Skeleton
Phase 1 — Auth, Models, and Ollama Connectivity
Phase 2 — Non-Streaming Chat + Usage Tracking
Phase 3 — Streaming and Vision
Phase 4 — User Usage API and Admin Limits
Phase 5 — Load Testing
Phase 6 — README and Final Demo
```

This keeps the plan short while preserving strong separation of concerns in the codebase.
