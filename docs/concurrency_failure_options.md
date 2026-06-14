# Concurrent Chat Failure Options

## Context

The observed log pattern is mixed chat successes followed by upstream failures:

```text
INFO:app.services.chat_proxy:chat.completed
INFO:httpx:HTTP Request: POST http://localhost:11434/v1/chat/completions "HTTP/1.1 200 OK"
WARNING:app.clients.ollama:ollama.request_failed
ERROR:app.services.chat_proxy:chat.failed
```

This happens under bursty concurrent real-Ollama chat load. The take-home scope asks
for a minimal proxy that can demonstrate proxy-level concurrency, while reporting
real Ollama results separately because local generation is hardware-bound.

## Inspected

- `project_description.md`
- `fastapi_ollama_proxy_lean_plan.md`
- `README.md`, `testing.md`, `changelog.md`
- `app/clients/ollama.py`
- `app/services/chat_proxy.py`
- `app/services/limits.py`
- `app/services/usage.py`
- `app/db.py`
- `app/config.py`
- `app/api/deps.py`
- `app/api/routes/chat.py`
- `app/repositories/users.py`
- `app/repositories/models.py`
- `app/repositories/limits.py`
- `app/repositories/usage.py`
- `scripts/load_test.py`
- `scripts/mock_ollama.py`
- `tests/test_phase0.py` through `tests/test_phase5.py`

## Evidence Gathered

- `git status --short` was clean before this note.
- `python3 -m pytest -q` passed: 28 tests.
- Mock upstream, single Uvicorn worker, 400 requests at concurrency 200:
  - 400 successes, 0 failures, 400 usage events.
  - p95 latency about 2.94s, p99 about 3.07s.
- Real Ollama, `llama3.2:1b`, 10 requests at concurrency 2, `max_tokens=1`:
  - 10 successes, 0 failures.
- Real Ollama, 100 requests at concurrency 100, `max_tokens=1`:
  - 100 successes, 0 failures, p99 about 2.78s.
- Real Ollama, 300 requests at concurrency 300, `max_tokens=1`:
  - 300 successes, 0 failures, p99 about 7.34s.
- Real Ollama, 100 requests at concurrency 100, `max_tokens=16`:
  - 69 successes, 31 failures, p95/p99 about 11.7s.
  - Usage event delta was 69, matching successful requests.
  - Proxy logs matched the user's pattern: `ollama.request_failed` followed by
    `chat.failed`.
- Direct Ollama-only diagnostic with 100 concurrent requests, `max_tokens=16`,
  and a 10-second HTTPX timeout:
  - 53 successes, 47 `ReadTimeout` failures.
  - Timeout failures clustered just over 10 seconds.

## Ranked Root Cause Candidates

1. **Real Ollama queue/generation latency exceeds the proxy's 10-second upstream timeout.**
   Evidence is strong. The failure reproduces against Ollama directly with
   `ReadTimeout`, and the proxy failure threshold appears when output size pushes
   p95/p99 above 10 seconds. Mock upstream does not fail.

2. **The proxy allows more simultaneous upstream requests than local Ollama can
   service predictably.**
   Evidence is strong but secondary. A few hundred one-token requests can complete,
   but larger completions create enough queueing for some requests to exceed the
   timeout. The current app has no upstream concurrency gate.

3. **Per-request `httpx.AsyncClient` creation adds avoidable connection churn.**
   Evidence is moderate. `app/clients/ollama.py` creates a fresh client for every
   chat call, so burst load creates many short-lived connection pools. This is not
   the direct reproduced failure by itself, but it makes high-concurrency behavior
   noisier and less efficient.

4. **SQLite persistence contention.**
   Evidence is low for the observed `ollama.request_failed` logs. SQLite uses WAL
   and a 30-second busy timeout, and usage event counts matched successful requests
   in the reproductions. Still, synchronous database work contributes to latency
   and could surface separately as failed responses after upstream success if the
   host is heavily loaded.

5. **Limit enforcement races under concurrency.**
   Evidence is low for this symptom. Limit rejections have distinct `429` behavior
   and were not present in these runs. Current request-rate checks are also based
   on completed successful usage, so they are not a protection against an initial
   burst with no prior usage.

## Evidence That Would Distinguish Remaining Cases

- Log the upstream exception class in `ollama.request_failed` without prompts or
  tokens. `ReadTimeout` would confirm the primary path in normal app logs.
- Compare the same real-Ollama run with `OLLAMA_TIMEOUT_SECONDS=60` if a timeout
  setting is added. If failures disappear while latency remains high, the cause is
  timeout/queueing rather than proxy correctness.
- Compare the same real-Ollama run with an upstream concurrency cap of 1, 2, 4, and
  8. If error rate drops to zero while total duration grows, Ollama saturation is
  the bottleneck.
- Run the mock overhead test with artificial mock latency greater than 10 seconds.
  If the proxy fails similarly, timeout behavior is confirmed independent of model
  generation.
- Watch `usage_events` and `usage_totals` deltas after each run. Mismatches would
  suggest persistence issues; matching deltas point back to upstream failures.

## Minimal Fix Options

### Option 1: Make the upstream timeout configurable and raise the default

Add `OLLAMA_TIMEOUT_SECONDS` to settings and pass it into `OllamaClient`. Use a
larger default for local real-Ollama testing, such as 60 seconds. Keep streaming
read timeout as unbounded, as it is today.

Tradeoffs:

- Smallest code change.
- Easy to defend: local model generation is slow and hardware-bound.
- Converts many 502s into slower successes.
- Does not protect Ollama from excessive simultaneous work.

### Option 2: Add a small in-process upstream concurrency gate

Use an `asyncio.Semaphore` around the real Ollama call, with a configurable
`OLLAMA_MAX_CONCURRENCY` default such as 4 or 8. Requests wait inside the proxy
instead of all hitting Ollama at once.

Tradeoffs:

- Still small and defensible for a local take-home proxy.
- Directly addresses saturation and keeps tail latency more predictable.
- Total wall-clock time increases under bursts.
- In-process only. With multiple Uvicorn workers, the true cap is per worker
  unless a shared queue is introduced, which is out of scope.

### Option 3: Return `429`/`503` immediately when local upstream capacity is full

Use a bounded semaphore and reject when no slot is available, with a clear
OpenAI-style error such as `server_overloaded`.

Tradeoffs:

- Prevents timeouts and unbounded queueing.
- Minimal compared with a durable queue.
- Changes semantics from "wait and maybe succeed" to "fail fast under overload".
- Less friendly for demos that expect all requests to eventually complete.

## Recommendation

Use **Option 1 plus a very small version of Option 2**:

1. Add configurable upstream timeout, defaulting to 60 seconds.
2. Add configurable upstream concurrency, defaulting conservatively for local
   Ollama, such as 4 or 8.
3. Document that mock upstream demonstrates proxy overhead, while real Ollama load
   tests should be reported with model, `max_tokens`, concurrency, timeout, and
   local hardware caveats.

If only one change is allowed, choose **Option 1**. It directly addresses the
reproduced `ReadTimeout` failure with the smallest diff. The concurrency gate is
the better operational behavior, but it is slightly more policy than plumbing.

## What Not To Do Yet

- Do not build a durable request queue.
- Do not add Redis/Postgres only for this symptom.
- Do not add broad retry logic around generation requests; retries can multiply
  Ollama load and duplicate expensive work.
- Do not treat real-Ollama hundreds-of-RPS as the proxy-overhead benchmark.
- Do not hide upstream saturation by only increasing Uvicorn workers.
- Do not record failed upstream requests as successful usage.

## Suggested Implementation Tasks

1. Add `ollama_timeout_seconds` and optionally `ollama_max_concurrency` to
   `Settings.from_env()`.
2. Pass the configured timeout into `OllamaClient` from `app/api/deps.py`.
3. If adding the concurrency gate, create one app-scoped semaphore during startup
   or attach a small `OllamaConcurrencyLimiter` to `app.state`, then use it around
   `create_chat_completion()` and stream setup.
4. Improve `ollama.request_failed` metadata to include safe exception class names,
   for example `ReadTimeout`, `ConnectError`, or `PoolTimeout`.
5. Add focused tests for configured timeout propagation and safe timeout logging.
6. Update `testing.md` with real-Ollama load-test guidance for timeout,
   concurrency, and `max_tokens`.

## Suggested Verification

Run the existing suite:

```bash
python3 -m pytest -q
python3 -m ruff check .
```

Run proxy-overhead with mock Ollama:

```bash
DATABASE_PATH=/tmp/replit-v3-load.sqlite3 python3 scripts/seed_dev_data.py
python3 -m uvicorn scripts.mock_ollama:create_app --factory --host 127.0.0.1 --port 11435 --no-access-log
DATABASE_PATH=/tmp/replit-v3-load.sqlite3 OLLAMA_BASE_URL=http://127.0.0.1:11435/v1 uvicorn app.main:app --host 127.0.0.1 --port 8000 --no-access-log
python3 scripts/load_test.py --mode proxy-overhead --proxy-url http://127.0.0.1:8000 --requests 400 --concurrency 200 --clear-limits --timeout-seconds 30
```

Run real Ollama with a clear before/after comparison:

```bash
DATABASE_PATH=/tmp/replit-v3-real-load.sqlite3 python3 scripts/seed_dev_data.py
DATABASE_PATH=/tmp/replit-v3-real-load.sqlite3 uvicorn app.main:app --host 127.0.0.1 --port 8000 --no-access-log
python3 scripts/load_test.py --mode real-ollama --proxy-url http://127.0.0.1:8000 --model llama3.2:1b --requests 100 --concurrency 100 --max-tokens 16 --clear-limits --timeout-seconds 90
```

Expected after the minimal fix:

- Mock overhead remains at 0 error rate with usage events matching successes.
- Real Ollama should either complete more requests successfully with the longer
  timeout, or show controlled overload behavior if a concurrency gate/rejection
  policy is added.
- Usage event count should equal successful request count.
