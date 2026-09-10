# Cryptiq

Deterministic cryptographic static-analysis backend.

Cryptiq analyses a repository at an exact commit and produces reproducible
findings about its use of cryptography. The engine is deterministic: the same
commit and the same rule set always yield the same findings.

## Local setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

cp .env.example .env

alembic upgrade head
RUN_WORKER=true uvicorn app.main:app --port 8000
```

`RUN_WORKER=true` (the default) runs the scan worker in-process with the API,
so queued scans execute without a separate process.

Then:

```bash
curl http://localhost:8000/health
curl http://localhost:8000/api/v1/health
```

## CLI

`cryptiq` is a thin client of the running HTTP API — it never imports the
engine or the database. Install it with `pip install -e ".[dev]"` (console
script `cryptiq`), or run `python -m app.cli`.

```bash
cryptiq scan https://github.com/pyca/cryptography 1f903f5ed2e5e316f345a927555e48535829d8de
cryptiq scan-status <scan_id>
cryptiq findings <scan_id> --algorithm rsa --priority high --page 1
cryptiq finding <finding_id>
cryptiq review-queue --status open
cryptiq review-update <review_id> --status in_review --assignee alice
cryptiq demo        # submit + poll + summarise the acceptance scan
```

Global `--api-url` (or `$CRYPTIQ_API_URL`, default
`http://localhost:8000/api/v1`). Every command takes `--json`, which emits the
API schema unchanged. Exit codes: `0` ok, `1` failure, `2` bad arguments,
`3` scan failed, `4` not found. See `../DEMO_RUNBOOK.md` for the full demo
flow and `../CLI_AUDIT.md` for design notes.

## Frontend

The React frontend lives in `../frontend` (`npm run dev`, port 5173) and
consumes the `/api/v1/scans`, `/api/v1/findings` and `/api/v1/review-queue`
endpoints.

## Tests

```bash
pytest                                    # unit, integration and security tests
CRYPTIQ_RUN_NETWORK_TESTS=1 pytest -m network   # opt-in, reaches github.com
ruff check .
```

## Pipeline

```
Repository -> exact commit -> source snapshot -> file discovery
  -> Python AST parser -> cryptographic rules -> source evidence
  -> bounded impact -> migration review priority -> fingerprint
```

`app/engine/pipeline.py` runs the whole chain over one extracted snapshot.
The snapshot exists only inside `async with ingest_commit(...)`, so every
stage that reads source runs within that block.

Rules implemented: RSA, ECDSA, Ed25519, ECDH, X25519, AES and hashes, all
against the Python `cryptography` library.

A finding separates what was observed from what was inferred: the algorithm,
API, location and source excerpt can be checked against the file, while the
cryptographic role, the post-quantum review path, the impact and the priority
follow from them. `FRONTEND_BACKEND_CONTRACT.md` records the response shape.

Persistence, the scan API (`POST /scans` → `202` queued / `200` cached), the
in-process worker, review items and the review queue are all implemented and
exercised by the CLI and frontend.

AI explanation: `POST /findings/{id}/explanation` (with a `GET` alias) generates
a bounded, structured natural-language explanation of an **already-established**
finding through Gemini, cached per `finding fingerprint + prompt version +
model`. It never discovers, re-classifies or overrides a deterministic value.
With no `GEMINI_API_KEY` set it returns a controlled `503
AI_EXPLANATION_UNAVAILABLE` and every finding stays fully usable. See
`../AI_EXPLANATION.md`.

See `MERGE_AUDIT.md` for how this repository was assembled (historical; paths in
it predate this workspace) and `../FINAL_AUDIT.md` for the current architecture.
