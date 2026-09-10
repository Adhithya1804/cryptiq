# Cryptiq Demo Runbook

Everything needed to run Cryptiq end to end for a demo: backend, worker,
frontend, CLI, and the exact repository and commit to analyse.

## The key point for judges

> **Cryptiq does not ask AI to discover cryptographic usage.**
> The deterministic engine discovers source-backed cryptographic evidence
> first — every finding quotes the line of code it came from, at an exact
> commit, and is reproducible. AI is only an explanation layer on top of
> findings that already exist: `POST /findings/{id}/explanation` sends one
> already-established finding to Gemini and returns a bounded, structured
> restatement, cached per finding fingerprint. It cannot change a detected
> value, and with no `GEMINI_API_KEY` set it returns a controlled
> `503 AI_EXPLANATION_UNAVAILABLE` while every finding stays fully usable.
> See `AI_EXPLANATION.md`.

## Demo repository and commit

```
Repository: https://github.com/pyca/cryptography
Commit:     1f903f5ed2e5e316f345a927555e48535829d8de
```

A completed scan of this exact commit is already persisted in
`cryptiq/cryptiq.db` (1042 findings, 132 review items). Re-submitting it
returns instantly from cache, which is what makes it a reliable demo.

## 1. Backend + worker

The worker runs **in-process** with the API when `RUN_WORKER=true` (the
default). One command starts both:

```bash
cd cryptiq
python -m venv .venv && source .venv/bin/activate   # first time only
pip install -e ".[dev]"                              # first time only
alembic upgrade head                                 # first time only

RUN_WORKER=true uvicorn app.main:app --port 8000
```

Check it is up:

```bash
curl -s http://localhost:8000/api/v1/health
# {"status":"ok","service":"cryptiq","version":"0.1.0"}
```

To run the worker as a separate process instead, start the API with
`RUN_WORKER=false` and run the worker loop yourself (`app.worker.worker_loop`).
For the demo, the in-process worker is simplest.

## 2. Frontend

```bash
cd frontend
npm install            # first time only
npm run dev            # http://localhost:5173
```

`frontend/.env.development.local` already points the client at
`http://localhost:8000/api/v1`.

## 3. CLI

Installed as the `cryptiq` console script (`pip install -e ".[dev]"` in the
backend venv), or run as `python -m app.cli`.

```bash
cd cryptiq && source .venv/bin/activate

# one command that does the whole flow:
python -m app.cli demo
```

Point at a non-default backend with `--api-url` or `$CRYPTIQ_API_URL`.

## Demo flow (manual, step by step)

### a. Submit the scan — shows cache reuse

```bash
python -m app.cli scan https://github.com/pyca/cryptography \
  1f903f5ed2e5e316f345a927555e48535829d8de
```

Expected on a **fresh** database:

```
Cryptiq Scan
Repository: pyca/cryptography
Commit: 1f903f5ed2e5e316f345a927555e48535829d8de
Status: QUEUED
Scan ID: <uuid>
```

Expected when the acceptance scan is **already persisted** (the normal case):

```
Status: CACHED
Scan ID: f763cc56-0c17-4bc9-87d2-4114198cf8a0
Existing result reused.
```

`CACHED` proves the engine is a pure function of the seven-part scan identity
(provider, owner, name, commit, parser version, ruleset version, PQC ruleset
version): an identical request does no new work.

### b. Watch it run to completion

```bash
python -m app.cli scan-status <scan_id>
```

Statuses cycle `QUEUED → RUNNING → COMPLETED` (or `FAILED` with an
`error_code` / `error_message`, never a stack trace). On the acceptance
commit the terminal state is:

```
Status:           COMPLETED
Files analyzed:   241
Findings:         1042
Severity:         critical=0 high=136 medium=906 low=0
```

### c. Expected finding count range

- Acceptance commit `1f903f5…`: **1042 findings**, **132 review items**
  (migration candidates get an `OPEN` review item when the scan completes).
- Roughly: hundreds to low-thousands of findings for a crypto-heavy Python
  repo of this size. A count of 0 or a handful means the wrong commit or a
  failed ingest.

### d. Inspect findings (server-side filtering + pagination)

```bash
python -m app.cli findings <scan_id> --page-size 10
python -m app.cli findings <scan_id> --algorithm rsa --priority high
python -m app.cli findings <scan_id> --role digital_signature --page 2
```

Footer shows `Page X / N` and `Total findings: <count>`. Filters are sent to
the API as query params; the CLI never downloads everything and filters
locally.

### e. Open one finding — demonstrate evidence, role, PQC, priority

```bash
python -m app.cli finding <finding_id>
```

The output is the API's evidence hierarchy, unmodified:

- **Observed** — rule id, algorithm, primitive, library, API, operation,
  file, line range, and the **source excerpt** quoted verbatim from the
  repository at that commit. *This is the "source-backed evidence" claim.*
- **Inference** — the cryptographic **role** (`DIGITAL_SIGNATURE`,
  `KEY_ESTABLISHMENT`, …), the rationale, and the confidence. Deterministic:
  `app/engine/roles/classifier.py` maps (algorithm, operation) to a role.
- **Migration** — the **PQC review path** (e.g. `ML-DSA / SLH-DSA` for
  signatures, `ML-KEM` for key establishment) and whether it is a migration
  candidate. Deterministic lookup in `app/engine/pqc/mapper.py`.
- **Impact** — the bounded, statically-observed blast radius (nodes +
  relationships).
- **Priority** — level, score, and the list of reasons. Deterministic scorer
  in `app/engine/priority/`.
- **Review** — the current review state, or `N/A (no review opened)`. Nulls
  render as `N/A`; nothing is fabricated.

Good findings to show on the acceptance commit: any ECDSA/Ed25519/RSA
`SIGN`/`VERIFY` (role `DIGITAL_SIGNATURE`, path `ML-DSA / SLH-DSA`, HIGH
priority with a "broken by Shor's algorithm" reason) versus a SHA-1/SHA-256
`HASH` (role `HASH`, path `HASH / POLICY REVIEW`, lower priority, no Shor
reason) — the queue separates migration candidates from inventory.

### f. Review queue

```bash
python -m app.cli review-queue --page 1 --page-size 10
python -m app.cli review-queue --priority high --algorithm rsa
```

Footer: `Review items: <count>` (132 on the acceptance commit).

Optional — move one item through a valid transition:

```bash
python -m app.cli review-update <review_id> --status in_review --assignee alice
python -m app.cli review-update <review_id> --status resolved
```

Only transitions the backend allows succeed; an illegal one prints
`A review cannot move from X to Y.` and exits 1.

### g. JSON mode (for scripting / piping)

Every command accepts `--json` and prints the **exact API schema** — no second
representation:

```bash
python -m app.cli findings <scan_id> --json | jq '.total'
python -m app.cli finding <finding_id> --json | jq '.observed.source_excerpt'
```

## Exit codes

| Code | Meaning |
| --- | --- |
| 0 | success |
| 1 | general / user-facing failure (backend unreachable, rejected request, illegal review transition) |
| 2 | invalid command or arguments |
| 3 | scan failed (`scan-status` / `demo` on a `FAILED` scan) |
| 4 | requested resource not found |

No expected error prints a Python traceback.

## Test commands

```bash
# backend
cd cryptiq && source .venv/bin/activate
python -m pytest            # 735 passed, 33 skipped
python -m ruff check .      # clean

# frontend
cd frontend
npm test                   # 55 passed
npm run typecheck
npm run lint
```

## Data sanity check (STEP 14)

Verified against the persisted acceptance scan
(`f763cc56-0c17-4bc9-87d2-4114198cf8a0`):

- Every finding carries evidence with a non-empty `source_excerpt`, a real
  `rule_id`, and `parser_version` / `ruleset_version` stamps.
- Source paths are real repository paths
  (`src/cryptography/hazmat/primitives/serialization/ssh.py`, …) and line
  numbers point at the actual call site.
- Fingerprints are stable 64-char hex digests; re-submitting the commit hits
  the cache instead of producing a second scan.
- Duplicate observations are deduplicated by fingerprint (1042 distinct
  findings).
- Roles, PQC review paths, priorities and their reason lists are produced by
  the deterministic engine stages, not stored free-text.
- 132 review items exist, one per migration-candidate finding.

No analysis rule was changed. No correctness defect was found during this
phase.
