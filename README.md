# FastAPI Ollama Proxy

Phase 0 project skeleton for the Replit take-home assignment.

## Run

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Then check:

```bash
curl http://localhost:8000/healthz
```

