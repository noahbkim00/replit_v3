PYTHON ?= python3
VENV ?= .venv
VENV_PYTHON := $(VENV)/bin/python
RUN ?= $(VENV_PYTHON)
PIP ?= $(RUN) -m pip

HOST ?= 127.0.0.1
PORT ?= 8000
BASE_URL ?= http://$(HOST):$(PORT)
OLLAMA_BASE_URL ?= http://localhost:11434/v1
DATABASE_PATH ?= data/proxy.sqlite3
DEMO_DATABASE_PATH ?= /tmp/replit-v3-demo.sqlite3
OLLAMA_TIMEOUT_SECONDS ?= 90
OLLAMA_MAX_CONCURRENCY ?= 4

USER_A_TOKEN ?= dev-token-user-a
USER_B_TOKEN ?= dev-token-user-b
ADMIN_TOKEN ?= dev-token-admin

TEXT_MODEL ?= llama3.2:1b
VISION_MODEL ?= moondream
DEMO ?= standard
REQUESTS ?= 300
CONCURRENCY ?= 50
LIMITED_ALLOWED ?= 150

DEMO_COMMON_ARGS = --proxy-url $(BASE_URL) --api-key $(USER_A_TOKEN) --timeout-seconds $(OLLAMA_TIMEOUT_SECONDS)
DEMO_MODEL_ARGS = --text-model $(TEXT_MODEL) --vision-model $(VISION_MODEL)
DEMO_ADMIN_ARGS = --admin-api-key $(ADMIN_TOKEN)

.DEFAULT_GOAL := help
.PHONY: help install setup seed start start-demo doctor ollama-pull ollama-check test test-file lint format check demo demo-standard demo-streaming demo-usage demo-limits demo-concurrency demo-load demos demos-full mock-ollama load-test reset-demo-db

help:
	@printf "%s\n" "FastAPI Ollama Proxy Make targets"
	@printf "%s\n" ""
	@printf "%s\n" "Setup:"
	@printf "%s\n" "  make install          Create .venv and install .[dev]"
	@printf "%s\n" "  make setup            Install deps, seed dev data, print model guidance"
	@printf "%s\n" "  make seed             Seed dev users/tokens/models into DATABASE_PATH"
	@printf "%s\n" "  make ollama-pull      Pull llama3.2:1b and moondream"
	@printf "%s\n" ""
	@printf "%s\n" "Run:"
	@printf "%s\n" "  make start            Start proxy on HOST:PORT"
	@printf "%s\n" "  make start-demo       Start proxy with DEMO_DATABASE_PATH"
	@printf "%s\n" "  make doctor           Check local prerequisites and service reachability"
	@printf "%s\n" ""
	@printf "%s\n" "Quality:"
	@printf "%s\n" "  make test             Run pytest unit suite"
	@printf "%s\n" "  make test-file TEST=tests/test_usage_and_limits_api.py"
	@printf "%s\n" "  make lint             Run ruff check"
	@printf "%s\n" "  make format           Run ruff format"
	@printf "%s\n" "  make check            Run lint and tests"
	@printf "%s\n" ""
	@printf "%s\n" "Demos:"
	@printf "%s\n" "  make demo DEMO=standard"
	@printf "%s\n" "  make demo-standard | demo-streaming | demo-usage | demo-limits"
	@printf "%s\n" "  make demo-concurrency | demo-load"
	@printf "%s\n" "  make demos            Run standard, streaming, usage, limits"
	@printf "%s\n" "  make demos-full       Run demos plus concurrency and load"
	@printf "%s\n" ""
	@printf "%s\n" "Common variables:"
	@printf "%s\n" "  PORT=8000 BASE_URL=http://127.0.0.1:8000 DATABASE_PATH=data/proxy.sqlite3"
	@printf "%s\n" "  USER_A_TOKEN=dev-token-user-a USER_B_TOKEN=dev-token-user-b ADMIN_TOKEN=dev-token-admin"

install:
	$(PYTHON) -m venv $(VENV)
	$(PIP) install --upgrade pip
	$(PIP) install -e ".[dev]"

setup: install seed
	@printf "%s\n" "Next: run 'make ollama-pull' if models are not installed."
	@printf "%s\n" "Start Ollama separately with: ollama serve"
	@printf "%s\n" "Start the proxy with: make start"

seed:
	DATABASE_PATH=$(DATABASE_PATH) $(RUN) scripts/seed_dev_data.py

start:
	DATABASE_PATH=$(DATABASE_PATH) \
	OLLAMA_BASE_URL=$(OLLAMA_BASE_URL) \
	OLLAMA_TIMEOUT_SECONDS=$(OLLAMA_TIMEOUT_SECONDS) \
	OLLAMA_MAX_CONCURRENCY=$(OLLAMA_MAX_CONCURRENCY) \
	$(RUN) -m uvicorn app.main:app --host $(HOST) --port $(PORT)

start-demo:
	DATABASE_PATH=$(DEMO_DATABASE_PATH) \
	OLLAMA_BASE_URL=$(OLLAMA_BASE_URL) \
	OLLAMA_TIMEOUT_SECONDS=$(OLLAMA_TIMEOUT_SECONDS) \
	OLLAMA_MAX_CONCURRENCY=$(OLLAMA_MAX_CONCURRENCY) \
	$(RUN) -m uvicorn app.main:app --host $(HOST) --port $(PORT) --no-access-log

doctor:
	@printf "%s\n" "Python runner:"
	@$(RUN) --version || { printf "%s\n" "Missing Python runner. Run 'make install' or override RUN=python3."; exit 1; }
	@printf "%s\n" ""
	@printf "%s\n" "Python dependencies:"
	@$(RUN) -c 'import fastapi, httpx, openai, pydantic, uvicorn; import app.main; print("Project imports OK")'
	@printf "%s\n" ""
	@printf "%s\n" "Ollama CLI:"
	@command -v ollama >/dev/null && ollama --version || printf "%s\n" "Ollama CLI not found. Install Ollama if you want to run real demos."
	@printf "%s\n" ""
	@printf "%s\n" "Proxy health:"
	@BASE_URL=$(BASE_URL) $(RUN) -c 'exec("import os, httpx\nurl = os.environ[\"BASE_URL\"].rstrip(\"/\") + \"/healthz\"\ntry:\n    r = httpx.get(url, timeout=2)\n    r.raise_for_status()\n    print(\"Proxy reachable:\", url)\nexcept Exception as exc:\n    print(f\"Proxy not reachable at {url}. Start it with: make start ({exc})\")")'

ollama-pull:
	@command -v ollama >/dev/null || { printf "%s\n" "Missing ollama CLI. Install Ollama, then rerun make ollama-pull."; exit 1; }
	ollama pull $(TEXT_MODEL)
	ollama pull $(VISION_MODEL)

ollama-check:
	OLLAMA_BASE_URL=$(OLLAMA_BASE_URL) $(RUN) -c 'import os, httpx; url=os.environ["OLLAMA_BASE_URL"].rstrip("/") + "/models"; r=httpx.get(url, timeout=5); r.raise_for_status(); print("Ollama reachable:", url)'

test:
	$(RUN) -m pytest -q

test-file:
	@test -n "$(TEST)" || { printf "%s\n" "Usage: make test-file TEST=tests/test_usage_and_limits_api.py"; exit 2; }
	$(RUN) -m pytest $(TEST) -q

lint:
	$(RUN) -m ruff check .

format:
	$(RUN) -m ruff format .

check: lint test

demo:
	@case "$(DEMO)" in \
		standard|streaming|usage|limits|concurrency|load) $(MAKE) demo-$(DEMO) ;; \
		*) printf "%s\n" "Unknown DEMO=$(DEMO). Use standard, streaming, usage, limits, concurrency, or load."; exit 2 ;; \
	esac

demo-standard:
	$(RUN) scripts/demo_standard.py $(DEMO_COMMON_ARGS) $(DEMO_MODEL_ARGS)

demo-streaming:
	$(RUN) scripts/demo_streaming.py $(DEMO_COMMON_ARGS) $(DEMO_MODEL_ARGS)

demo-usage:
	$(RUN) scripts/demo_usage.py $(DEMO_COMMON_ARGS) $(DEMO_MODEL_ARGS) $(DEMO_ADMIN_ARGS)

demo-limits:
	$(RUN) scripts/demo_limits.py $(DEMO_COMMON_ARGS) $(DEMO_MODEL_ARGS) $(DEMO_ADMIN_ARGS) --user-id user_a

demo-concurrency:
	$(RUN) scripts/demo_concurrency.py $(DEMO_COMMON_ARGS) $(DEMO_MODEL_ARGS) $(DEMO_ADMIN_ARGS)

demo-load:
	$(RUN) scripts/demo_load_test.py --proxy-url $(BASE_URL) --api-key $(USER_A_TOKEN) --limited-api-key $(USER_B_TOKEN) --admin-api-key $(ADMIN_TOKEN) --model $(TEXT_MODEL) --requests $(REQUESTS) --concurrency $(CONCURRENCY) --limited-allowed $(LIMITED_ALLOWED) --timeout-seconds $(OLLAMA_TIMEOUT_SECONDS)

demos: demo-standard demo-streaming demo-usage demo-limits

demos-full: demos demo-concurrency demo-load

mock-ollama:
	$(RUN) scripts/mock_ollama.py --host 127.0.0.1 --port 11435

load-test:
	$(RUN) scripts/load_test.py --mode proxy-overhead --proxy-url $(BASE_URL) --token $(USER_A_TOKEN) --admin-token $(ADMIN_TOKEN) --model $(TEXT_MODEL) --requests $(REQUESTS) --concurrency $(CONCURRENCY) --clear-limits

reset-demo-db:
	@test "$(CONFIRM)" = "reset-demo-db" || { printf "%s\n" "Refusing to reset demo DB. Run: make reset-demo-db CONFIRM=reset-demo-db"; exit 2; }
	rm -f "$(DEMO_DATABASE_PATH)" "$(DEMO_DATABASE_PATH)-shm" "$(DEMO_DATABASE_PATH)-wal"
