# Changelog

## Changes Logged on Empty — Testing and Demo Overhaul

### Changes Made

- Added shared pytest fixtures in `tests/conftest.py` for temp settings, seeded
  real FastAPI apps, real SQLite usage row helpers, auth headers, chat payloads,
  SSE chunks, and method-level `OllamaClient` stubs.
- Renamed phase-numbered unit tests to capability-based filenames.
- Updated HTTP-path tests to use the shared fixtures while preserving real auth,
  repositories, services, SQLite usage/limit code, and FastAPI routing.
- Kept direct service-level tests only for the Ollama concurrency limiter and
  stream-generator close behavior.
- Added real demo scripts:
  - `scripts/demo_standard.py`
  - `scripts/demo_streaming.py`
  - `scripts/demo_limits.py`
  - `scripts/demo_usage.py`
  - `scripts/demo_concurrency.py`
  - `scripts/demo_load_test.py`
- Added `scripts/demo_helpers.py` for common OpenAI client setup, proxy API
  helpers, Lorem Picsum image encoding, usage snapshots, limit updates, and
  PASS/FAIL output.
- Made `/v1/models` include upstream `:latest` entries when the untagged model is
  allowlisted, so local Ollama installs that report `moondream:latest` satisfy
  the required `moondream` demo preflight.
- Updated the load-demo metric tests to exercise `scripts/demo_load_test.py`
  without contacting Ollama.
- Replaced phase-oriented README/testing guidance with concise unit-test,
  local-Ollama, fresh-DB, and demo commands.

### Verification Steps Performed

- `python3 -m pytest tests/test_chat_completions_usage.py
  tests/test_streaming_vision_and_request_validation.py
  tests/test_usage_and_limits_api.py
  tests/test_atomic_limit_reservations_and_client_lifecycle.py
  tests/test_auth_models_and_seed_data.py -q` passed with 27 tests.
- `python3 -m pytest tests/test_demo_load_test_metrics.py -q` passed with 3
  tests.
- `python3 -m pytest -q` passed with 35 tests.
- `python3 -m ruff format .` passed and reformatted files.
- `python3 -m ruff check .` passed.
- `python3 -m py_compile scripts/demo_helpers.py scripts/demo_standard.py
  scripts/demo_streaming.py scripts/demo_limits.py scripts/demo_usage.py
  scripts/demo_concurrency.py scripts/demo_load_test.py` passed.
- Help checks passed for all new demo scripts:
  - `python3 scripts/demo_standard.py --help`
  - `python3 scripts/demo_streaming.py --help`
  - `python3 scripts/demo_limits.py --help`
  - `python3 scripts/demo_usage.py --help`
  - `python3 scripts/demo_concurrency.py --help`
  - `python3 scripts/demo_load_test.py --help`
- Live real-Ollama demos against an already running proxy on port 8000 passed:
  - `python3 scripts/demo_standard.py --proxy-url http://127.0.0.1:8000
    --timeout-seconds 120`
  - `python3 scripts/demo_streaming.py --proxy-url http://127.0.0.1:8000
    --timeout-seconds 120`
  - `python3 scripts/demo_usage.py --proxy-url http://127.0.0.1:8000
    --timeout-seconds 120`
  - `python3 scripts/demo_concurrency.py --proxy-url http://127.0.0.1:8000
    --timeout-seconds 120 --requests-per-user 2`
- Live real-Ollama demos against a fresh seeded proxy on port 8032 passed:
  - `python3 scripts/demo_limits.py --proxy-url http://127.0.0.1:8032
    --timeout-seconds 120`
  - `python3 scripts/demo_load_test.py --proxy-url http://127.0.0.1:8032
    --timeout-seconds 120 --requests 4 --concurrency 2 --limited-allowed 2`
- After tightening model preflight, a fresh proxy on port 8033 listed
  `moondream:latest` and `python3 scripts/demo_standard.py --proxy-url
  http://127.0.0.1:8033 --timeout-seconds 120` passed.
- After adding the limited-scenario fresh-window guard, `python3
  scripts/demo_load_test.py --proxy-url http://127.0.0.1:8033 --timeout-seconds
  120 --requests 4 --concurrency 2 --limited-allowed 2` passed.

### Deviations From the Plan

- The load demo uses `user_a` for the no-limit scenario and `user_b` for the
  limited scenario so recent no-limit traffic cannot consume the limited
  request-per-minute window.
- Existing `scripts/load_test.py` and `scripts/mock_ollama.py` were left in
  place as legacy/internal utilities, but README/testing docs no longer present
  them as the submitted proof path.
- `/v1/models` filtering now treats an upstream `model:latest` ID as matching an
  untagged allowlist entry such as `model`.
- `python` is not present on this machine outside a virtualenv, so verification
  commands were run with `python3`.

### Deviation Rationale

- A single script cannot deterministically run no-limit traffic and then enforce
  a lower request-per-minute cap on the same user without waiting for the rolling
  60-second window or resetting the database; separate seeded users keep the
  proof deterministic and still exercise the same real proxy code.
- Ollama accepts untagged aliases like `moondream` even when its OpenAI-compatible
  model list reports `moondream:latest`; treating those as equivalent keeps
  model listing, allowlisting, and demo preflight aligned with local Ollama
  behavior.
- The old mock/load utilities may still be useful for internal development, and
  removing them is unnecessary for the requested demo overhaul.

## Changes Logged on Empty — Atomic Limits and Shared Ollama Client

### Changes Made

- Added `QuotaRepository` and `UsageReservation` for atomic chat quota reservation
  with `BEGIN IMMEDIATE`.
- Changed chat limit enforcement to reserve one `usage_events` row with
  `status='reserved'` before calling Ollama, then finalize it to `success` or
  `failed`.
- Counted in-flight reservations during request-per-minute and token-cap checks so
  concurrent requests cannot all pass the same preflight window.
- Preserved successful usage totals by updating `usage_totals` only when a
  reservation finalizes as `success`.
- Made upstream failures and interrupted streams auditable as zero-token
  `status='failed'` usage events.
- Finalized clean streaming completions without final usage as `success` with zero
  usage, matching the selected plan's naming choice.
- Wrapped hot-path SQLite work from async services with `asyncio.to_thread`,
  including model allowlist lookup, quota reservation, and quota finalization.
- Removed the stale non-atomic limit preflight method from `LimitService` and the
  now-unused direct usage writer dependency from `ChatProxyService`.
- Converted usage/admin DB-only routes from `async def` to `def` so FastAPI runs
  their sync repository work in a threadpool.
- Changed `OllamaClient` to own one long-lived `httpx.AsyncClient`, added
  `aclose()`, initialized a shared client in FastAPI lifespan, and injected it
  through dependencies.
- Added focused tests for concurrent request-rate enforcement, concurrent token-cap
  enforcement, failed stream auditing, and shared Ollama client reuse/shutdown.
- Updated `testing.md` with the exact focused concurrency/lifecycle checks,
  broader regression command, full test/lint commands, and a small mocked manual
  load-test workflow.

### Verification Steps Performed

- `python3 -m pytest tests/test_atomic_limits_and_client_lifecycle.py -q` failed
  before implementation with four expected behavioral failures: concurrent request
  limits allowed five upstream calls, concurrent token limits allowed five upstream
  calls, interrupted streams recorded no failed event, and no shared
  `app.state.ollama_client` existed.
- `python3 -m pytest tests/test_atomic_limits_and_client_lifecycle.py -q` passed
  after implementation with 4 tests.
- `python3 -m pytest tests/test_phase2.py tests/test_phase3.py tests/test_phase4.py
  tests/test_concurrency_controls.py -q` initially failed on stale expectations
  for failed audit rows and the old fake limit-service interface.
- `python3 -m pytest tests/test_phase2.py tests/test_phase3.py tests/test_phase4.py
  tests/test_concurrency_controls.py tests/test_atomic_limits_and_client_lifecycle.py
  -q` passed after updating tests with 23 tests.
- `python3 -m ruff check app tests/test_atomic_limits_and_client_lifecycle.py
  tests/test_concurrency_controls.py tests/test_phase2.py tests/test_phase3.py`
  initially failed on an unused `time` import in the new test module.
- `python3 -m ruff check app tests/test_atomic_limits_and_client_lifecycle.py
  tests/test_concurrency_controls.py tests/test_phase2.py tests/test_phase3.py`
  passed after removing the stale import.
- `python3 -m pytest -q` passed with 34 tests.
- `python3 -m ruff check .` passed.

### Deviations From the Plan

- No Redis/Postgres, background workers, queues, or unrelated architecture changes
  were added.
- Failed non-streaming upstream requests are also finalized as zero-token
  `status='failed'` events, not just failed streams.
- The previous `OllamaConcurrencyLimiter` remains in place alongside the shared
  client.
- A real Ollama/load-test run was not performed during this pass; mocked
  concurrency tests were added and passed.

### Deviation Rationale

- Finalizing non-streaming upstream failures follows the plan's reservation model
  and keeps all post-reservation upstream failures auditable without billing them.
- Keeping the existing concurrency limiter preserves the prior Phase 5 behavior
  while the shared HTTP client removes per-request client construction.
- Real Ollama throughput is hardware-bound and requires local server/model state.
  The new automated tests prove the selected atomic-limit behavior with mocked
  upstream calls, and `testing.md` documents the manual load-test commands.

## Changes Logged on Empty — Minimal Logging

### Changes Made

- Added `LOG_LEVEL` support through `Settings.log_level` while keeping the default
  at `INFO`.
- Configured stdlib logging in `create_app` and added a `proxy.startup` event after
  database initialization with non-secret configuration sanity fields.
- Added aggregate-safe auth logs for missing/invalid bearer auth and non-admin
  admin-route attempts.
- Added `chat.rejected` logs for oversized bodies, invalid JSON, and non-object
  JSON without logging raw request bodies.
- Added `limit.rejected` logs for request-per-minute, daily-token, and total-token
  rejections with safe limit counters.
- Added Ollama client failure logs for network/timeouts, HTTP status failures,
  invalid JSON, and invalid response shapes using endpoint names only.
- Added high-level non-streaming and streaming chat logs for success, expected
  client failures, upstream failures, stream completion with usage, and stream
  completion without usage.
- Added focused `caplog` assertions across Phase 0 through Phase 4 tests to verify
  expected log events and absence of bearer tokens, prompts, raw bodies, streamed
  chunk content, and base64 snippets.
- Updated `testing.md` with automated logging checks, manual log capture commands,
  expected event names, and explicit sensitive-content grep checks.

### Verification Steps Performed

- `python3 -m pytest tests/test_phase0.py tests/test_phase1.py tests/test_phase2.py
  tests/test_phase3.py tests/test_phase4.py -q` failed before implementation with
  17 missing-log assertion failures.
- `python3 -m pytest tests/test_phase0.py tests/test_phase1.py tests/test_phase2.py
  tests/test_phase3.py tests/test_phase4.py -q` passed after implementation with
  25 tests.
- `python3 -m ruff check app tests` initially failed on a stale unused
  `UpstreamServiceError` import in `tests/test_phase1.py`.
- `python3 -m ruff check app tests` passed after removing the stale import.
- `python3 -m pytest -q` passed with 28 tests.
- `python3 -m ruff check .` passed.

### Deviations From the Plan

- No implementation deviations from `docs/minimal_logging_plan.md`.
- The optional local Uvicorn smoke check was documented in `testing.md` but not run
  as part of this automated verification pass.

### Deviation Rationale

- The local smoke check depends on running a long-lived server and local Ollama
  state. The automated tests cover the logging paths with mocked upstream behavior
  and an upstream-unavailable client path, while `testing.md` provides exact manual
  commands for local inspection.

## Changes Logged on Empty — Phase 5

### Changes Made

- Added `scripts/mock_ollama.py`, a small FastAPI mock of Ollama's
  OpenAI-compatible `/v1/models` and `/v1/chat/completions` endpoints.
- The mock supports non-streaming and streaming chat responses, configurable model
  IDs, configurable synthetic latency, and deterministic usage token counts.
- Added `scripts/load_test.py`, an async HTTPX load runner for the proxy's
  `/v1/chat/completions` path.
- The load runner reports requests per second, p50 latency, p95 latency, p99
  latency, error rate, limit rejection rate, usage event delta, and usage-total
  comparison fields.
- Added load-test support for `proxy-overhead` and `real-ollama` modes so mock
  upstream results can be reported separately from hardware-bound local Ollama
  generation results.
- Added admin-limit setup options to the load runner: `--set-request-limit` for
  concurrent rejection tests and `--clear-limits` for resetting local runs.
- Added focused Phase 5 tests in `tests/test_phase5.py` for metric calculation,
  empty-result behavior, and CLI mode/limit argument parsing.
- Updated `testing.md` with Phase 5 automated checks, mock-server startup, proxy
  startup against the mock, proxy-overhead load-test commands, metric
  interpretation, concurrent limit-rejection checks, usage-event inspection, and
  real-Ollama load-test workflow.

### Verification Steps Performed

- `python3 -m pytest tests/test_phase5.py -q` failed before implementation with
  `ModuleNotFoundError: No module named 'scripts.load_test'`.
- `python3 -m pytest tests/test_phase5.py -q` passed after implementation with 3
  tests.
- `python3 -m pytest -q` passed after implementation with 26 tests.
- `python3 -m ruff check scripts/load_test.py scripts/mock_ollama.py
  tests/test_phase5.py` initially failed on import ordering in
  `scripts/mock_ollama.py`.
- `python3 -m ruff check scripts/mock_ollama.py --fix` fixed the import order.
- `python3 -m ruff check .` passed.
- `DATABASE_PATH=/tmp/replit-v3-phase5-smoke.sqlite3 python3
  scripts/seed_dev_data.py` passed and printed the development tokens.
- `python3 scripts/mock_ollama.py --host 127.0.0.1 --port 11435` started the mock
  Ollama server successfully.
- `DATABASE_PATH=/tmp/replit-v3-phase5-smoke.sqlite3
  OLLAMA_BASE_URL=http://127.0.0.1:11435/v1 uvicorn app.main:app --host
  127.0.0.1 --port 8025` started the proxy against the mock successfully.
- `python3 scripts/load_test.py --proxy-url http://127.0.0.1:8025 --requests 40
  --concurrency 10 --clear-limits` passed with 40 successful requests, 0.0 error
  rate, 40 usage events, and usage totals matching successes.
- `python3 scripts/load_test.py --proxy-url http://127.0.0.1:8025 --requests 12
  --concurrency 6 --set-request-limit 1` passed with 12 limit rejections, 1.0
  limit rejection rate, 0 usage events, and usage totals matching successes.
- `ollama list` showed local `llama3.2:1b` available.
- `DATABASE_PATH=/tmp/replit-v3-phase5-real.sqlite3 python3
  scripts/seed_dev_data.py` passed and printed the development tokens.
- `DATABASE_PATH=/tmp/replit-v3-phase5-real.sqlite3 uvicorn app.main:app --host
  127.0.0.1 --port 8026` started the proxy against local Ollama successfully.
- `python3 scripts/load_test.py --mode real-ollama --proxy-url
  http://127.0.0.1:8026 --requests 2 --concurrency 1 --model llama3.2:1b
  --max-tokens 1 --clear-limits --timeout-seconds 60` passed with 2 successful
  requests, 0.0 error rate, 2 usage events, and usage totals matching successes.
- `DATABASE_PATH=/tmp/replit-v3-phase5-workers.sqlite3 python3
  scripts/seed_dev_data.py` passed and printed the development tokens.
- `python3 -m uvicorn scripts.mock_ollama:create_app --factory --host 127.0.0.1
  --port 11436 --no-access-log` started the mock Ollama server successfully.
- `DATABASE_PATH=/tmp/replit-v3-phase5-workers.sqlite3
  OLLAMA_BASE_URL=http://127.0.0.1:11436/v1 uvicorn app.main:app --host
  127.0.0.1 --port 8028 --no-access-log --workers 4` started the proxy against
  the mock successfully.
- `python3 scripts/load_test.py --proxy-url http://127.0.0.1:8028 --requests 400
  --concurrency 200 --clear-limits --timeout-seconds 60` passed with 400
  successful requests, 0.0 error rate, 400 usage events, usage totals matching
  successes, and 229 RPS.

### Deviations From the Plan

- No proxy architecture changes were made for Phase 5.
- The repeatable hundreds-of-RPS proxy-overhead run uses Uvicorn runtime settings
  (`--workers 4` and `--no-access-log`) rather than changing application code.
- The real-Ollama verification was intentionally a tiny smoke test rather than a
  high-throughput run.

### Deviation Rationale

- Multiple Uvicorn workers are a deployment/runtime configuration and keep Phase 5
  scoped to load testing while still exercising auth, model validation, limit
  checks, Ollama forwarding, and SQLite usage recording through the real proxy path.
- Local Ollama generation is hardware-bound and not evidence of proxy overhead, so
  it is reported separately from the mock-upstream test.

## Changes Logged on Empty — Phase 4

### Changes Made

- Added a `role` column to `users` with migration support for existing SQLite
  databases.
- Added a seeded admin user and `dev-token-admin` development API token.
- Added a `user_limits` table and limit repository for `requests_per_minute`,
  `daily_tokens`, and `total_tokens`.
- Added usage repository read methods for per-user summaries, per-user events,
  recent successful request counts, daily token totals, and all-time token totals.
- Added a usage service and implemented authenticated `GET /usage` and
  `GET /usage/events`.
- Added admin authentication and implemented `PUT /admin/users/{user_id}/limits`,
  `GET /admin/users/{user_id}/limits`, and
  `GET /admin/users/{user_id}/usage`.
- Replaced the Phase 2 no-op limit service with preflight limit enforcement before
  Ollama forwarding for non-streaming and streaming chat paths.
- Added `429` OpenAI-style error responses with `rate_limit_exceeded` when request
  rate, daily token, or total token limits would be exceeded.
- Preserved existing usage recording after successful Ollama completion and avoided
  creating successful usage events for limit-rejected requests.
- Added focused Phase 4 tests in `tests/test_phase4.py` for user usage visibility,
  admin limit CRUD, admin usage lookup, request-rate enforcement, token-cap
  enforcement, and upstream-call prevention for rejected requests.
- Updated `testing.md` with Phase 4 automated checks, usage API examples, user
  isolation checks, admin limit examples, and rejection examples.

### Verification Steps Performed

- `python3 -m pytest tests/test_phase4.py -q` failed before implementation with
  `404 Not Found` for the missing usage and admin endpoints.
- `python3 -m pytest tests/test_phase4.py -q` initially errored after partial
  implementation due to a misplaced `usage_totals` upsert in
  `app/repositories/usage.py`.
- `python3 -m pytest tests/test_phase4.py -q` passed after fixing the repository
  write path with 4 tests.
- `python3 -m pytest -q` initially failed because the Phase 1 seed test still
  expected only two non-admin users and two tokens.
- `python3 -m pytest -q` passed after updating the seed test for the admin user and
  token with 23 tests.
- `python3 -m ruff check .` passed.

### Deviations From the Plan

- Token preflight uses `max_tokens` as the projected token usage. If `max_tokens` is
  omitted or not an integer, the projection is `0`.
- Phase 4 live local-Ollama smoke testing was not performed as part of this phase
  execution.

### Deviation Rationale

- The Phase 4 plan explicitly calls for estimating token usage from `max_tokens`.
  Treating missing or invalid `max_tokens` as `0` keeps the implementation small and
  avoids inventing tokenizer behavior that Ollama may not match.
- Local Ollama availability and pulled model state are machine-dependent. The
  automated tests mock the upstream client and verify the important proxy behavior,
  including that rejected requests do not call Ollama; `testing.md` documents exact
  local commands for manual verification.

## Changes Logged on Empty — Phase 3

### Changes Made

- Added configurable chat request body limiting with an 8 MiB default for local
  base64 image-data use.
- Changed the chat route to parse and size-check raw JSON before handing request
  bodies to the chat proxy service.
- Added `OllamaClient.stream_chat_completion()` for streaming
  `POST /chat/completions` responses from Ollama.
- Added streaming support for `POST /v1/chat/completions` and
  `POST /chat/completions` using `StreamingResponse`.
- Forced `stream_options.include_usage=true` for streaming requests while preserving
  other client-provided stream options.
- Added SSE usage extraction for streaming responses and records at most one usage
  event after a completed stream when Ollama provides final usage.
- Preserved non-streaming chat behavior and usage recording.
- Added OpenAI-style vision message validation for `image_url` parts, accepting
  base64 data URLs and rejecting remote image URLs without downloading them.
- Added focused Phase 3 tests in `tests/test_phase3.py`.
- Removed the obsolete Phase 2 test and documentation that expected `stream=true`
  to be rejected.
- Updated `testing.md` with Phase 3 automated checks, streaming OpenAI-client and
  curl examples, SQLite usage checks, and a Lorem Picsum base64 data-URL vision
  demo for `moondream`.

### Verification Steps Performed

- `python3 -m pytest tests/test_phase3.py -q` failed before implementation with
  missing `OllamaClient.stream_chat_completion`, missing remote-image validation,
  missing body-size enforcement, and default FastAPI invalid-JSON handling.
- `python3 -m pytest tests/test_phase3.py -q` passed after implementation with
  7 tests.
- `python3 -m pytest -q` initially failed because the obsolete Phase 2
  stream-rejection test still expected `400`.
- `python3 -m pytest -q` passed after updating the stale Phase 2 test suite with
  19 tests.
- `python3 -m ruff check .` initially failed on import ordering in
  `app/services/chat_proxy.py`.
- `python3 -m ruff check app/services/chat_proxy.py` passed after fixing the import
  order.
- `python3 -m pytest -q` passed with 19 tests.
- `python3 -m ruff check .` passed.
- `DATABASE_PATH=/tmp/replit-v3-phase3-seed.sqlite3 python3 scripts/seed_dev_data.py`
  passed and printed both development tokens.
- `ollama list` showed local `llama3.2:1b` and `moondream:latest` models available.
- `DATABASE_PATH=/tmp/replit-v3-phase3-live.sqlite3 python3 scripts/seed_dev_data.py`
  passed and seeded a temporary live-test database.
- `DATABASE_PATH=/tmp/replit-v3-phase3-live.sqlite3 uvicorn app.main:app --host
  127.0.0.1 --port 8013` started successfully for live smoke testing.
- A live OpenAI-client streaming request to `http://127.0.0.1:8013/v1` with
  `model="llama3.2:1b"` returned incremental content and usage
  `prompt_tokens=32`, `completion_tokens=6`, `total_tokens=38`; SQLite recorded
  `user_a|llama3.2:1b|32|6|38|success`.
- A live OpenAI-client vision request to `http://127.0.0.1:8013/v1` with
  `model="moondream"` and a Lorem Picsum image encoded as a base64 data URL
  returned a vision response and usage `prompt_tokens=745`, `completion_tokens=32`,
  `total_tokens=777`; SQLite recorded `user_a|moondream|745|32|777|success`.

### Deviations From the Plan

- Remote image URLs are rejected rather than forwarded to Ollama.
- Failed or interrupted streaming requests are not recorded as usage events when
  Ollama does not provide final usage.

### Deviation Rationale

- Rejecting remote image URLs is the simplest way to guarantee the proxy does not
  download remote images and to avoid relying on upstream remote-fetch behavior.
- Skipping records for streams without final usage avoids inventing token usage for
  interrupted requests. Successful billable streaming requests are recorded when
  Ollama sends final usage.

## Changes Logged on Empty — Phase 2

### Changes Made

- Added SQLite `usage_events` and `usage_totals` tables for successful chat usage.
- Added a usage repository that records one event and maintains per-user/per-model totals.
- Added a no-op `LimitService` preflight placeholder for the Phase 2 chat flow.
- Added a chat proxy service that validates the requested model against the allowlist,
  rejects `stream=true`, calls Ollama through the client layer, extracts token usage,
  records usage, and returns the upstream response.
- Added `OllamaClient.create_chat_completion()` for `POST /chat/completions`.
- Added authenticated `POST /v1/chat/completions` and `POST /chat/completions` routes.
- Added clean `400` OpenAI-style error responses for invalid Phase 2 chat requests.
- Added focused Phase 2 tests in `tests/test_phase2.py`.
- Updated `testing.md` with Phase 2 automated checks, local OpenAI-client testing,
  usage persistence checks, invalid-auth no-billing checks, stream rejection, and
  upstream-failure behavior.

### Verification Steps Performed

- `python3 -m pytest tests/test_phase2.py -q` failed before implementation with
  `AttributeError: <class 'app.clients.ollama.OllamaClient'> has no attribute
  'create_chat_completion'`.
- `python3 -m pytest tests/test_phase2.py -q` passed after implementation with 6 tests.
- `python3 -m pytest -q` passed after implementation with 13 tests.
- `python3 -m ruff check .` initially failed on import ordering in `app/main.py`.
- `python3 -m ruff check . --fix` fixed 1 import-order issue.
- `python3 -m pytest tests/test_phase2.py -q` passed after import formatting with 6 tests.
- `python3 -m pytest -q` passed after import formatting with 13 tests.
- `python3 -m ruff check .` passed after import formatting.
- `DATABASE_PATH=/tmp/replit-v3-phase2-seed.sqlite3 python3 scripts/seed_dev_data.py`
  passed and printed both development tokens.

### Deviations From the Plan

- Real local-Ollama verification was not performed as part of this phase execution.
- Failed upstream chat requests are not recorded as usage events in Phase 2.

### Deviation Rationale

- Local Ollama availability and pulled model state are machine-dependent. The automated
  tests use a mocked upstream path, while `testing.md` documents exact local-Ollama
  OpenAI-client and upstream-unavailable checks for manual verification.
- Phase 2 requires extracting usage from successful Ollama responses and not inventing
  token usage for failed upstream requests. Not recording failed upstream attempts keeps
  token billing unambiguous; `status` is currently recorded as `success` for billable
  usage events and can support richer event types in later phases.

## Changes Logged on Empty — Phase 1

### Changes Made

- Added SQLite initialization for `users`, `api_tokens`, and `model_allowlist`.
- Added repository modules for user/token lookup and model allowlist access.
- Added a development seed script that creates `user_a`, `user_b`, dev API tokens, and the `llama3.2`, `llama3.2:1b`, and `moondream` allowlist entries.
- Added bearer-token authentication dependency with `401` responses for missing or invalid tokens.
- Added an Ollama client wrapper for `GET /v1/models` forwarding.
- Added a model service that fetches Ollama models and filters the response to the SQLite allowlist.
- Added authenticated `GET /v1/models` and `GET /models` routes.
- Added a clean `502` upstream error response for Ollama connectivity and invalid upstream response failures.
- Added focused Phase 1 tests in `tests/test_phase1.py`.
- Added a regression test proving `scripts/seed_dev_data.py` does not need `pydantic` just to resolve `DATABASE_PATH`.
- Added explicit setuptools package discovery so `python -m pip install -e ".[dev]"` installs the flat-layout app without trying to package `data/`.
- Updated `testing.md` with Phase 1 seed, auth, model route, and upstream-unavailable verification steps.

### Verification Steps Performed

- `python3 -m pytest tests/test_phase1.py -q` failed before implementation with `ImportError: cannot import name 'OllamaClient'`.
- `python3 -m pytest tests/test_phase1.py -q` passed after implementation with 4 tests.
- `python3 -m pytest` passed with 6 tests.
- `python3 -m ruff check .` initially failed on import ordering; `python3 -m ruff check . --fix` fixed 3 import-order issues.
- `python3 -m ruff check .` passed after import ordering was fixed.
- `DATABASE_PATH=/tmp/replit-v3-phase1-seed.sqlite3 python3 scripts/seed_dev_data.py` initially failed because running the script directly put `scripts/` on `sys.path`; the script now adds the project root before importing `app`.
- `DATABASE_PATH=/tmp/replit-v3-phase1-seed.sqlite3 python3 scripts/seed_dev_data.py` passed after the script entry-point fix and printed both dev tokens.
- `python3 -m pytest tests/test_phase1.py::test_seed_script_does_not_require_pydantic_for_database_path -q` failed before the follow-up fix with `ModuleNotFoundError: No module named 'pydantic'`.
- `python3 -m pytest tests/test_phase1.py::test_seed_script_does_not_require_pydantic_for_database_path -q` passed after the script stopped importing `app.config`.
- `DATABASE_PATH=/tmp/replit-v3-phase1-user-seed.sqlite3 python3 scripts/seed_dev_data.py` passed after the follow-up fix.
- `python3 -m pytest` passed with 7 tests after the follow-up fix.
- `python3 -m ruff check .` passed after the follow-up fix.
- `.venv/bin/python -m pip install -e ".[dev]"` initially failed because setuptools discovered multiple top-level packages in the flat layout: `app` and `data`.
- `.venv/bin/python -m pip install -e ".[dev]"` passed after adding explicit setuptools package discovery for `app*`.
- `.venv/bin/python -m pytest tests/test_phase1.py` passed with 5 tests.
- `.venv/bin/python -m pytest` passed with 7 tests.
- `.venv/bin/python -m ruff check .` passed.

### Deviations From the Plan

- Local real-Ollama verification was not added as a required automated test; the automated test suite uses a mocked Ollama client path.

### Deviation Rationale

- Local Ollama availability and pulled model state are machine-dependent. The code still forwards through `clients/ollama.py`, and `testing.md` documents exact manual local-Ollama checks plus an upstream-unavailable check.

## Changes Logged on Empty — Phase 0

### Changes Made

- Added the Phase 0 FastAPI project skeleton under `app/`.
- Added Pydantic-backed config loading from environment variables.
- Added SQLite initialization with a metadata table and WAL mode.
- Added `GET /healthz`, returning `{"status": "ok"}`.
- Added Python project setup in `pyproject.toml` with FastAPI, Uvicorn, HTTPX, Pydantic, OpenAI, Pytest, and Ruff.
- Added basic local setup files: `README.md`, `.env.example`, and `.gitignore`.
- Added Phase 0 tests in `tests/test_phase0.py`.

### Verification Steps Performed

- `python3 -m pytest tests/test_phase0.py` failed before implementation with `ModuleNotFoundError: No module named 'app.config'`.
- `python3 -m pytest tests/test_phase0.py` passed after implementation.
- `python3 -m pytest` passed with 2 tests.
- `python3 -m ruff check .` passed with no issues.
- `python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8000` started successfully.
- `curl -sS -i http://localhost:8000/healthz` returned `HTTP/1.1 200 OK` and `{"status":"ok"}`.

### Deviations From the Plan

- No functional endpoints beyond `GET /healthz` were implemented.
- Later-phase route/client/service/repository modules are placeholders only.
- No auth, model endpoints, chat completions, usage tracking, limits, streaming, vision, or load testing was added.

### Deviation Rationale

- These boundaries keep the implementation strictly scoped to Phase 0 while preserving the planned package structure for later phases.
