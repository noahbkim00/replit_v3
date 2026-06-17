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

### Demo Tokens

Demo targets use separate seeded users so usage totals, request windows, limits,
and audit events from one demo do not affect another.

| Demo | User ID | Token |
| --- | --- | --- |
| Standard | `demo_standard` | `dev-token-demo-standard` |
| Streaming | `demo_streaming` | `dev-token-demo-streaming` |
| Usage A | `demo_usage_a` | `dev-token-demo-usage-a` |
| Usage B | `demo_usage_b` | `dev-token-demo-usage-b` |
| Limits | `demo_limits` | `dev-token-demo-limits` |
| Usage Report | `demo_report` | `dev-token-demo-report` |
| Concurrency A | `demo_concurrency_a` | `dev-token-demo-concurrency-a` |
| Concurrency B | `demo_concurrency_b` | `dev-token-demo-concurrency-b` |
| Load Open | `demo_load_open` | `dev-token-demo-load-open` |
| Load Limited | `demo_load_limited` | `dev-token-demo-load-limited` |

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
make demo-report
make demo-concurrency
make demo-load REQUESTS=300 CONCURRENCY=50 LIMITED_ALLOWED=150
```

Run the non-load demo set:

```bash
make demos
```

See `testing.md` for the full testing and demo workflow.

## Usage Report

The bonus feature is a read-only HTML report for usage and limits. You can open
the browser helper directly and enter a seeded user token, or use admin mode
with the admin token to view all users associated with that admin:

```bash
open http://127.0.0.1:8000/usage/report/browser
```

The helper sends tokens only as `Authorization: Bearer ...` headers with
JavaScript `fetch`; it does not put tokens in URLs, cookies, or browser storage.

The underlying user report endpoint still requires bearer auth and is useful for
curl-based inspection:

```bash
curl http://127.0.0.1:8000/usage/report \
  -H "Authorization: Bearer dev-token-demo-report" \
  -o /tmp/replit-v3-usage-report.html
open /tmp/replit-v3-usage-report.html
```

Admins can render an associated-users report:

```bash
curl http://127.0.0.1:8000/admin/usage/report \
  -H "Authorization: Bearer dev-token-admin" \
  -o /tmp/replit-v3-admin-usage-report.html
open /tmp/replit-v3-admin-usage-report.html
```

Admins can also render a detail report for one associated user:

```bash
curl http://127.0.0.1:8000/admin/users/demo_report/usage/report \
  -H "Authorization: Bearer dev-token-admin"
```

### End-To-End Usage Report Test

Use this exact flow to test the report with real Ollama, real proxy requests,
and a fresh SQLite database. The examples use port `8121` so they do not assume
that port `8000` is free.

1. In terminal 1, start Ollama and leave it running:

```bash
ollama serve
```

If the models are not installed yet, run this once from another terminal:

```bash
make ollama-pull
```

2. In terminal 2, create a fresh report database, seed tokens, and start the
   proxy. Leave this terminal running:

```bash
rm -f /tmp/replit-v3-report-test.sqlite3*
DATABASE_PATH=/tmp/replit-v3-report-test.sqlite3 make seed

DATABASE_PATH=/tmp/replit-v3-report-test.sqlite3 \
OLLAMA_BASE_URL=http://localhost:11434/v1 \
make start PORT=8121 BASE_URL=http://127.0.0.1:8121
```

3. In terminal 3, run the usage report demo. This sends a real chat request
   through the proxy using `dev-token-demo-report`, sets sample limits for
   `demo_report`, fetches the user report and admin report, and writes HTML
   files to `/tmp`:

```bash
make demo-report PORT=8121 BASE_URL=http://127.0.0.1:8121
```

Expected output includes:

```text
usage-report:user PASS
usage-report:admin PASS
usage-report:browser PASS
```

4. Optional but useful: add more real usage rows for multiple users so the admin
   report has more than one active user:

```bash
.venv/bin/python - <<'PY'
from openai import OpenAI

base_url = "http://127.0.0.1:8121/v1"
requests = [
    ("dev-token-user-a", "Reply with exactly: user a report row one"),
    ("dev-token-user-a", "Reply with exactly: user a report row two"),
    ("dev-token-user-b", "Reply with exactly: user b report row one"),
    ("dev-token-demo-report", "Reply with exactly: demo report row one"),
]

for token, prompt in requests:
    client = OpenAI(base_url=base_url, api_key=token, timeout=90)
    response = client.chat.completions.create(
        model="llama3.2:1b",
        messages=[{"role": "user", "content": prompt}],
        temperature=0,
        max_tokens=16,
    )
    print(token, response.usage)
PY
```

5. Open the browser helper:

```bash
open http://127.0.0.1:8121/usage/report/browser
```

6. Test these browser modes and tokens:

| Mode | Token | Expected report |
| --- | --- | --- |
| `User` | `dev-token-demo-report` | Report for `demo_report` only. |
| `User` | `dev-token-user-a` | Report for `user_a` only. |
| `Admin` | `dev-token-admin` | Associated-users report for `admin`, including `user_a`, `user_b`, and `demo_report`. |
| `Admin` | `dev-token-user-a` | Error: admin credentials required. |

The browser helper sends the token as an `Authorization: Bearer ...` header. Do
not put tokens in the URL.

7. Verify the same reports with curl if you want to inspect raw HTML responses:

```bash
curl http://127.0.0.1:8121/usage/report \
  -H "Authorization: Bearer dev-token-demo-report"

curl http://127.0.0.1:8121/admin/usage/report \
  -H "Authorization: Bearer dev-token-admin"
```

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
| `make demo-report` | Generate usage, fetch the HTML report, and write it to `/tmp`. |
| `make demo-load` | Run the heavier load demo separately. |

## Troubleshooting

- Missing dependencies: run `make install`.
- Proxy unavailable: run `make start`.
- Port 8000 occupied: run `make start PORT=8001`.
- Ollama unavailable: start Ollama with `ollama serve` or open the Ollama app.
- Missing models: run `make ollama-pull`.
- Demo limit state is stale: run `make reset-demo-db CONFIRM=reset-demo-db`,
  reseed the demo database, or wait 60 seconds. This can happen when rerunning
  the same limited demo within the rolling request window.

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
