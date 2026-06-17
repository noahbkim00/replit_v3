# FastAPI Ollama Proxy

OpenAI-compatible FastAPI proxy for local Ollama with bearer-token auth,
per-user usage tracking, admin-configurable limits, streaming chat, and vision
requests.

## Download From GitHub

Clone the repository with Git:

```bash
git clone https://github.com/noahbkim00/replit_v3.git
cd replit_v3
```

If you do not want to use Git, download a ZIP from GitHub:

1. Open `https://github.com/noahbkim00/replit_v3`.
2. Click `Code`.
3. Click `Download ZIP`.
4. Unzip the file.
5. Open a terminal in the unzipped `replit_v3` directory.

## Prerequisites

Install these before setup:

- Python 3.11 or newer.
- `make`.
- Ollama for real model demos.
- Git, if cloning instead of downloading the ZIP.

Check the local tools:

```bash
python3 --version
make --version
```

Install Ollama from `https://ollama.com/download`, then either open the Ollama
desktop app or start it from a separate terminal:

```bash
ollama serve
```

## Quick Start

From the repository directory:

```bash
make setup
make ollama-pull
make start
```

`make setup` creates `.venv`, installs the package with dev tools, and seeds the
development database. `make ollama-pull` downloads the required local models:
`llama3.2:1b` and `moondream`.

Keep the proxy running in that terminal. In another terminal, verify it:

```bash
curl http://127.0.0.1:8000/healthz
```

Expected response:

```json
{"status":"ok"}
```

## Development Tokens

The seed script creates these fixed development API tokens:

- User A: `dev-token-user-a`
- User B: `dev-token-user-b`
- Admin: `dev-token-admin`

Example OpenAI-compatible request:

```bash
curl http://127.0.0.1:8000/v1/models \
  -H "Authorization: Bearer dev-token-user-a"
```

## Run The Proxy

Default:

```bash
make start
```

Use a different port:

```bash
make start PORT=8001
```

Useful defaults:

- Proxy URL: `http://127.0.0.1:8000`
- Ollama OpenAI-compatible URL: `http://localhost:11434/v1`
- SQLite database: `data/proxy.sqlite3`
- Text model: `llama3.2:1b`
- Vision model: `moondream`

## Tests And Checks

Unit tests do not require real Ollama; they stub only the Ollama client
boundary.

```bash
make test
make lint
make check
```

Run one focused test file:

```bash
make test-file TEST=tests/test_usage_and_limits_api.py
```

## Real Ollama Demos

Real demo targets require:

- Ollama running.
- `make ollama-pull` completed.
- Proxy running with seeded data.

For deterministic demo output, use a fresh demo database:

```bash
make reset-demo-db CONFIRM=reset-demo-db
DATABASE_PATH=/tmp/replit-v3-demo.sqlite3 make seed
make start-demo
```

In another terminal, run one demo:

```bash
make demo DEMO=standard
```

Available demos:

```bash
make demo-standard
make demo-streaming
make demo-usage
make demo-limits
make demo-concurrency
make demo-load REQUESTS=300 CONCURRENCY=50 LIMITED_ALLOWED=150
```

Run the non-load demo set:

```bash
make demos
```

See `testing.md` for the full testing and demo workflow.

## Common Make Commands

| Command | Description |
| --- | --- |
| `make help` | Print available targets and common variables. |
| `make install` | Create `.venv` and install the package with dev tools. |
| `make setup` | Install dependencies and seed development users/tokens/models. |
| `make seed` | Seed development data into `DATABASE_PATH`. |
| `make start` | Start the proxy on `127.0.0.1:8000`. |
| `make start-demo` | Start the proxy against `/tmp/replit-v3-demo.sqlite3`. |
| `make doctor` | Check local runner, imports, Ollama CLI, and proxy health. |
| `make ollama-pull` | Pull `llama3.2:1b` and `moondream`. |
| `make ollama-check` | Check whether Ollama is reachable. |
| `make test` | Run unit tests; real Ollama is not required. |
| `make lint` | Run Ruff. |
| `make format` | Format with Ruff. |
| `make check` | Run Ruff and unit tests. |
| `make demo DEMO=standard` | Run one selected demo. |
| `make demos` | Run non-load real-Ollama demos. |
| `make demo-load` | Run the heavier load demo separately. |

## Troubleshooting

- Missing dependencies: run `make install`.
- Proxy unavailable: run `make start`.
- Port 8000 occupied: run `make start PORT=8001`.
- Ollama unavailable: start Ollama with `ollama serve` or open the Ollama app.
- Missing models: run `make ollama-pull`.
- Demo limit state is stale: run `make reset-demo-db CONFIRM=reset-demo-db`,
  reseed the demo database, or wait 60 seconds.

`make doctor` is a quick local sanity check:

```bash
make doctor
```

## Without Make

The Makefile is a thin wrapper around the project tooling. Equivalent manual
setup commands are:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
python scripts/seed_dev_data.py
uvicorn app.main:app --host 127.0.0.1 --port 8000
```
