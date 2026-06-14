# Changelog

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
