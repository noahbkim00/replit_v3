# Minimal Logging Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add small, useful operational logging to the FastAPI/Ollama proxy without building an observability platform.

**Architecture:** Use Python stdlib `logging` with module-level loggers in the existing app layers. Log request flow outcomes and failures with safe metadata only; do not add middleware, persistence, metrics, tracing, structured logging dependencies, or dashboards.

**Tech Stack:** FastAPI, Python `logging`, pytest `caplog`, existing repository/service/client structure.

---

## Scope

Add logs for:

- App startup/config sanity without secrets.
- Authentication failures in aggregate-safe terms.
- Limit rejections.
- Upstream Ollama request failures.
- Non-streaming chat completion success/failure at a high level.
- Streaming completion end/failure.

Do not log:

- Bearer tokens or token hashes.
- Full prompts, message bodies, raw request bodies, raw response bodies, SSE chunks, or base64 image data.
- Authorization headers, cookies, or other secrets.
- User display names unless the team explicitly decides they are safe. `user.id`, model, route, status class, token counts, and latency are enough for this assignment.

## File Map

- Modify `app/config.py`: optional `log_level: str = "INFO"` setting from `LOG_LEVEL`, if the implementation wants explicit app log level control.
- Modify `app/main.py`: initialize stdlib logging once, log startup config sanity, and log handled upstream/client errors.
- Modify `app/api/deps.py`: log missing/invalid bearer auth and non-admin admin attempts.
- Modify `app/api/routes/chat.py`: log request body size rejections and invalid JSON/body shape rejections.
- Modify `app/services/limits.py`: log rate-limit and token-limit rejections before raising `ClientRequestError`.
- Modify `app/services/chat_proxy.py`: log chat/stream success and failures at a high level.
- Modify `app/clients/ollama.py`: log upstream failure categories with endpoint/status, not payloads.
- Test in existing phase test files, likely `tests/test_phase0.py`, `tests/test_phase2.py`, `tests/test_phase3.py`, and `tests/test_phase4.py`.

## Log Events and Levels

Use clear event names in each message so plain text logs remain searchable:

| Flow | Level | Location | Message/event | Safe fields |
| --- | --- | --- | --- | --- |
| Startup complete | `INFO` | `app/main.py` lifespan after `initialize_database` | `proxy.startup` | `app_name`, `database_path`, `ollama_base_url`, `max_request_body_bytes` |
| Missing bearer auth | `WARNING` | `app/api/deps.py::require_user` | `auth.failure` | `reason="missing_bearer"` |
| Invalid bearer auth | `WARNING` | `app/api/deps.py::require_user` | `auth.failure` | `reason="invalid_token"` |
| Non-admin uses admin route | `WARNING` | `app/api/deps.py::require_admin` | `auth.forbidden` | `user_id` |
| Body too large | `WARNING` | `app/api/routes/chat.py::_read_json_body` | `chat.rejected` | `reason="body_too_large"`, `limit_bytes`, `content_length` when available |
| Invalid JSON/body shape | `WARNING` | `app/api/routes/chat.py::_read_json_body` | `chat.rejected` | `reason="invalid_json"` or `reason="body_not_object"` |
| Limit rejected | `WARNING` | `app/services/limits.py` | `limit.rejected` | `user_id`, `limit_type`, current count/sum if already computed, configured limit, estimated tokens where relevant |
| Non-streaming chat success | `INFO` | `app/services/chat_proxy.py::create_chat_completion` after usage write | `chat.completed` | `user_id`, `model`, `stream=False`, `status="success"`, `prompt_tokens`, `completion_tokens`, `total_tokens`, `latency_ms` |
| Non-streaming chat validation/limit failure | `WARNING` | `app/services/chat_proxy.py::create_chat_completion` around validation/limit checks | `chat.failed` | `user_id`, `model` if valid, `stream=False`, `error_type`, `status_code` |
| Non-streaming upstream failure | `ERROR` | `app/services/chat_proxy.py::create_chat_completion` when `UpstreamServiceError` propagates | `chat.failed` | `user_id`, `model`, `stream=False`, `error_type="upstream_error"`, `latency_ms` |
| Streaming completion ended with usage | `INFO` | `app/services/chat_proxy.py::stream_chat_completion` after usage write | `chat.stream_completed` | `user_id`, `model`, `stream=True`, token counts, `latency_ms` |
| Streaming completed without usage | `WARNING` | `app/services/chat_proxy.py::stream_chat_completion` after loop when usage is missing | `chat.stream_completed_without_usage` | `user_id`, `model`, `latency_ms` |
| Streaming upstream failure/interruption | `ERROR` | `app/services/chat_proxy.py::stream_chat_completion` around async iteration | `chat.stream_failed` | `user_id`, `model`, `error_type="upstream_error"`, `latency_ms` |
| Ollama network/timeout failure | `WARNING` | `app/clients/ollama.py` exception handlers | `ollama.request_failed` | `endpoint`, `reason="unavailable"` |
| Ollama HTTP failure | `WARNING` | `app/clients/ollama.py` exception handlers | `ollama.request_failed` | `endpoint`, `status_code` |
| Ollama invalid JSON/shape | `WARNING` | `app/clients/ollama.py` exception handlers/validation | `ollama.invalid_response` | `endpoint`, `reason` |

Prefer logger calls with `extra={...}` for fields, but keep the message itself readable, for example:

```python
logger.info(
    "chat.completed",
    extra={
        "user_id": user.id,
        "model": model,
        "stream": False,
        "total_tokens": usage.total_tokens,
        "latency_ms": round(latency_ms, 2),
    },
)
```

## Implementation Tasks

### Task 1: Add Startup Logging

**Files:**
- Modify `app/config.py`
- Modify `app/main.py`
- Test `tests/test_phase0.py`

- [ ] Add `log_level` to `Settings` with default `"INFO"` and read it from `LOG_LEVEL`.
- [ ] In `create_app`, configure stdlib logging minimally with `logging.basicConfig(level=getattr(logging, settings.log_level.upper(), logging.INFO))`.
- [ ] In the lifespan function, after `initialize_database(settings.database_path)`, log `proxy.startup` at `INFO`.
- [ ] Add a `caplog` test that starts the app and asserts the startup log exists and does not contain any token-like values.
- [ ] Run `python -m pytest tests/test_phase0.py -q`.

### Task 2: Add Auth and Request Rejection Logs

**Files:**
- Modify `app/api/deps.py`
- Modify `app/api/routes/chat.py`
- Test existing auth/body rejection tests in `tests/test_phase2.py`, `tests/test_phase3.py`, and `tests/test_phase4.py`

- [ ] Add module loggers.
- [ ] Log `auth.failure` at `WARNING` for missing bearer and invalid bearer cases before raising `HTTPException`.
- [ ] Log `auth.forbidden` at `WARNING` for non-admin users before raising `HTTPException`.
- [ ] Log `chat.rejected` at `WARNING` for body-size, invalid JSON, and non-object JSON failures.
- [ ] Add `caplog` assertions to existing rejection tests. Assert the token string and request prompt text are absent from captured logs.
- [ ] Run `python -m pytest tests/test_phase2.py tests/test_phase3.py tests/test_phase4.py -q`.

### Task 3: Add Limit Rejection Logs

**Files:**
- Modify `app/services/limits.py`
- Test `tests/test_phase4.py`

- [ ] In `_check_request_rate`, store the computed `recent_requests`; when rejecting, log `limit.rejected` at `WARNING` with `user_id`, `limit_type="requests_per_minute"`, `recent_requests`, and `limit`.
- [ ] In `_check_token_caps`, store computed daily/total token sums before each comparison; when rejecting, log `limit.rejected` at `WARNING` with `user_id`, `limit_type`, current tokens, estimated tokens, and limit.
- [ ] Add `caplog` checks to the existing request-per-minute and token-limit rejection tests.
- [ ] Run `python -m pytest tests/test_phase4.py -q`.

### Task 4: Add Ollama Failure Logs

**Files:**
- Modify `app/clients/ollama.py`
- Test `tests/test_phase1.py`, `tests/test_phase2.py`, and `tests/test_phase3.py`

- [ ] Add a small private helper if useful, such as `_log_upstream_failure(endpoint: str, reason: str, status_code: int | None = None)`.
- [ ] Log network/timeouts, HTTP status errors, invalid JSON, and invalid response shape at `WARNING`.
- [ ] Include only endpoint names such as `"/models"` and `"/chat/completions"` plus status/reason.
- [ ] Add or update tests for upstream failure paths with `caplog` assertions.
- [ ] Run `python -m pytest tests/test_phase1.py tests/test_phase2.py tests/test_phase3.py -q`.

### Task 5: Add Chat Flow Logs

**Files:**
- Modify `app/services/chat_proxy.py`
- Test `tests/test_phase2.py` and `tests/test_phase3.py`

- [ ] In non-streaming `create_chat_completion`, log `chat.completed` at `INFO` only after usage is recorded.
- [ ] For expected client failures after auth, log `chat.failed` at `WARNING` with safe metadata before re-raising. Keep this narrow to `ClientRequestError`.
- [ ] For upstream failures, log `chat.failed` at `ERROR` with safe metadata and latency before re-raising.
- [ ] In streaming `stream_chat_completion`, wrap async iteration so `UpstreamServiceError` logs `chat.stream_failed` at `ERROR` with latency.
- [ ] After a streaming loop completes, log `chat.stream_completed` at `INFO` when usage was recorded.
- [ ] If the stream completes without usage, log `chat.stream_completed_without_usage` at `WARNING`; keep current billing behavior unchanged unless a separate task explicitly changes it.
- [ ] Add `caplog` assertions to existing non-streaming success, upstream failure, streaming success, and interrupted stream tests.
- [ ] Run `python -m pytest tests/test_phase2.py tests/test_phase3.py -q`.

### Task 6: Full Verification

**Files:**
- No new code files beyond the above.

- [ ] Run `python -m pytest -q`.
- [ ] Run `python -m ruff check .`.
- [ ] Optional local smoke check:

```bash
python scripts/seed_dev_data.py
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

- [ ] Send one authenticated chat request and one invalid-token request, then inspect stdout logs for event names and absence of tokens/prompts.

## Privacy and Security Checklist

- No `Authorization` header logging.
- No token, token hash, or request header dumps.
- No raw `request_body`, `payload`, `response_body`, streamed `chunk`, or exception object repr if it could include payload data.
- No prompt text or message content.
- No base64 data URL or image bytes.
- No raw SQLite rows from usage events.
- Keep user identifiers to `user_id`; do not add display name unless explicitly approved.

## Open Questions and Risks

- `database_path` can reveal local filesystem layout. This is acceptable for local take-home logs, but omit it if these logs may be shared externally.
- Streaming failures after response headers are sent may still surface as server exceptions in tests. The logging task should observe and log them without changing existing response semantics.
- If `basicConfig` conflicts with Uvicorn logging in practice, keep module loggers and remove app-level configuration; `caplog` tests should still verify emitted records.

## Tiny Rollout Sequence

1. Startup logging and `LOG_LEVEL`.
2. Auth/request rejection logs.
3. Limit rejection logs.
4. Ollama client failure logs.
5. Chat success/failure and stream completion logs.
6. Full pytest/ruff verification and one manual smoke run.
