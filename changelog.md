# Changelog

## 2026-06-14 - Phase 0 project skeleton

### Changes made

- Added the initial FastAPI project skeleton using the predefined Phase 0 structure:
  - `app/main.py`
  - `app/core/`
  - `app/api/`
  - `app/api/routes/`
  - `app/clients/`
  - `app/domain/`
  - `app/schemas/`
  - `app/services/`
  - `app/repositories/`
  - `app/db/`
  - `app/middleware/`
  - `tests/`
  - `scripts/`
- Added environment-based configuration in `app/core/config.py` with the Phase 0 defaults:
  - `OLLAMA_BASE_URL=http://localhost:11434/v1`
  - `PORT=8000`
  - `DATABASE_URL=sqlite:///./proxy.db`
  - `ADMIN_TOKEN=dev-admin-token`
  - `MAX_REQUEST_BODY_BYTES=10485760`
- Added FastAPI app assembly in `app/main.py`.
- Added router assembly in `app/api/router.py`.
- Added the Phase 0 health route in `app/api/routes/health.py`.
- Added lightweight request ID and request size middleware.
- Added placeholder modules for later-phase routes, services, repositories, schemas, database helpers, scripts, and tests without implementing later-phase behavior.
- Added project packaging and dependency metadata in `pyproject.toml`.
- Added `.env.example`, `.gitignore`, `README.md`, and the generated `uv.lock`.
- Added a Phase 0 smoke test for `GET /healthz` in `tests/integration/test_health_route.py`.

### Verification performed

- Verified the smoke test failed before implementation:
  - Command: `uv run pytest tests/integration/test_health_route.py`
  - Result: failed with `ModuleNotFoundError: No module named 'app'`, confirming the test was exercising the missing Phase 0 app skeleton.
- Verified the focused health route test after implementation:
  - Command: `uv run pytest tests/integration/test_health_route.py`
  - Result: `1 passed`.
- Verified the full current test suite:
  - Command: `uv run pytest`
  - Result: `1 passed`.
- Verified linting:
  - Command: `uv run ruff check .`
  - Result: `All checks passed!`.
- Verified import boundaries with search checks:
  - Command: `rg "from app\.(api|services)|import app\.(api|services)" app/repositories app/db`
  - Result: no matches.
  - Command: `rg "from app\.repositories|import app\.repositories|from app\.clients|import app\.clients" app/api`
  - Result: no matches.
- Verified local Ollama prerequisites:
  - Command: `ollama list`
  - Result: `llama3.2:latest`, `llama3.2:1b`, and `moondream:latest` were present locally.
- Verified manual FastAPI startup and smoke endpoint:
  - Command: `uv run uvicorn app.main:app --port 8000`
  - Result: Uvicorn started on `http://127.0.0.1:8000`.
  - Command: `curl -sS -i http://127.0.0.1:8000/healthz`
  - Result: HTTP `200 OK` with body `{"status":"ok"}`.

### Deviations from the plan

- Used `uv run ...` for dependency installation and command execution rather than raw `pytest`, `ruff`, or `uvicorn` commands.
  - Reason: the repository started without an existing virtual environment or package manager state. `uv` created a local `.venv`, generated `uv.lock`, installed the declared dependencies from `pyproject.toml`, and made the verification commands reproducible.
- Added `pythonpath = ["."]` to the pytest configuration.
  - Reason: `uv run python -c "import app"` could import the local package, but pytest collection did not resolve the repository root consistently until the path was explicit. This keeps local test collection stable without changing application behavior.
- Used an async `httpx.ASGITransport` smoke test instead of FastAPI's synchronous `TestClient`.
  - Reason: the installed FastAPI/Starlette stack emitted a deprecation warning for `TestClient`; using `httpx.ASGITransport` keeps the Phase 0 test output clean while still exercising the ASGI app directly.
- Added lightweight middleware implementations in Phase 0 rather than empty middleware placeholder files.
  - Reason: the plan requires app assembly to register middleware and later phases rely on request ID and body-size boundaries. The implementations are intentionally minimal and do not add later-phase proxy behavior.
- Did not run `ollama pull llama3.2` or `ollama pull moondream`.
  - Reason: `ollama list` showed the required models were already installed locally, so pulling them again was unnecessary for Phase 0 validation.

### Explicitly deferred outside Phase 0

- `/v1/models` and `/models` proxy behavior.
- User authentication and admin authentication.
- Model allowlisting.
- Chat completions proxying.
- Streaming responses.
- Vision request handling.
- Usage persistence.
- Admin usage limits.
- Load testing and concurrency validation.
