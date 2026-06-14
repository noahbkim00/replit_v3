# Phase 0 Testing

Set up the local environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
```

Run the Phase 0 automated checks:

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
