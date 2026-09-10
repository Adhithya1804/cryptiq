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

`cryptiq` is the standalone CLI to the analysis engine. It runs in two modes
over the **same** engine — see [`CLI.md`](CLI.md) for the full reference.

**Local** (offline; runs the engine in-process, no API/DB/Docker needed):

```bash
cryptiq scan .                                   # working tree
cryptiq scan /path/to/repo --commit <sha>        # exact commit via `git archive`
cryptiq scan . --format sarif                    # valid SARIF 2.1.0
cryptiq diff --base <sha> --head <sha>           # fingerprint diff: NEW/FIXED/UNCHANGED
cryptiq version
```

**Remote** (thin HTTP client of a running Cryptiq API):

```bash
cryptiq scan https://github.com/org/repo --remote --commit <sha>
cryptiq scan https://github.com/org/repo --remote --commit <sha> --wait --format sarif
cryptiq scan-status <scan_id>
cryptiq findings <scan_id> --algorithm rsa --priority high
cryptiq finding <finding_id> --grouped
cryptiq review-queue --status open --json
cryptiq review-update <review_id> --status in_review --assignee alice
cryptiq demo        # submit + poll + summarise the acceptance scan
```

Install with `pip install -e ".[dev]"` (console script `cryptiq`) or run
`python -m app.cli`. Remote API URL: `--api-url`, then `$CRYPTIQ_API_URL`, then
`http://localhost:8000/api/v1`. Every command takes `--json`. Exit codes:
`0` ok / no blocking findings, `1` findings need attention (or generic remote
failure), `2` bad arguments, `3` operational error, `4` remote resource not
found. See [`CLI.md`](CLI.md), `../DEMO_RUNBOOK.md` and `../CLI_AUDIT.md`.

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

## Supported analysis scope

Cryptiq provides deterministic cryptographic migration analysis for **supported
APIs in the Python `cryptography` library**. The analysis engine — AST parsing,
role inference, PQC review-path mapping, impact and priority — is
library-agnostic; coverage is defined entirely by the rule set, which is
extensible to further cryptographic libraries by adding rules under
`app/engine/rules/`.

| | |
|---|---|
| **Language** | Python (`ast`-based; no target code is executed) |
| **Library** | `cryptography` (pyca) |
| **Rules** | RSA, ECDSA, Ed25519, ECDH, X25519, AES, hashes |
| **Not yet covered** | PyCryptodome (`Crypto.*`), PyNaCl (`nacl.*`), stdlib `hashlib`, DSA, DH, TLS/protocol recognition — tracked as future rule-set scope, not a defect |

A repository outside this scope (or one with no cryptography at all) scans
cleanly and returns zero findings rather than guesses — the engine is precise
about what it can establish from syntax and silent about the rest. Coverage of
additional libraries is additive: a new rule does not change any existing
finding or its fingerprint.

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
