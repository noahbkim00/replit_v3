# Changelog

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
