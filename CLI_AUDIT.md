# CLI Audit

Audit performed before implementing the developer/demo CLI (STEP 1).

## Existing CLI implementation

**None.** The repository had no command-line interface before this phase.

Searched `cryptiq/app/` and `cryptiq/tests/` for `argparse`, `typer`,
`click`, `__main__.py`, `add_parser`, `ArgumentParser`, and console-script
declarations:

- No `argparse` / `typer` / `click` import anywhere.
- No `__main__.py` module.
- `pyproject.toml` declared exactly one console script:
  `cryptiq-api = "app.main:run"` — a thin wrapper that runs
  `uvicorn app.main:app` for local development. It is not a CLI, it only
  starts the web server.
- `README.md` documented `curl` calls against the HTTP API, nothing else.

So there was no CLI to extend and no risk of duplication.

## Framework used

**`argparse` (standard library).** No new dependency was added. The only
third-party package the CLI needs is `httpx`, which is already a first-class
dependency of the backend.

## Architecture chosen (STEP 8)

The CLI is a **thin HTTP client of the running FastAPI backend**. It calls the
same `/api/v1` endpoints the React frontend uses:

```
cryptiq CLI ── httpx ──▶ FastAPI (/api/v1) ──▶ services ──▶ repositories ──▶ DB
                                          └──▶ in-process scan worker
```

Reasons for HTTP-client over direct service-layer imports:

- The engine, fingerprinting, evidence validation and review-transition rules
  all stay behind the API. The CLI cannot bypass them even by accident — it
  has no database session and never imports `app.engine` or `app.services`.
- The demo command needs to *poll a scan to completion*. Completion is done by
  the in-process worker that runs inside the API process (`RUN_WORKER=true`).
  A CLI holding its own session would queue a scan that nothing executes.
- STEP 8 explicitly blesses this: "If the CLI is calling HTTP locally, use the
  real FastAPI endpoints."
- STEP 13 requires running the CLI against the real local backend; an HTTP
  client is the faithful way to do that.

## Current commands (after this phase)

| Command | Endpoint(s) used | Purpose |
| --- | --- | --- |
| `cryptiq scan <repo_url> <commit_sha>` | `POST /scans` | Submit an exact repo+commit scan; prints `QUEUED` / `CACHED` and the scan id |
| `cryptiq scan-status <scan_id>` | `GET /scans/{id}` | Monitor a scan (status, commits, timestamps, finding count, error state) |
| `cryptiq findings <scan_id>` | `GET /scans/{id}/findings` | Server-filtered, paginated findings table |
| `cryptiq finding <finding_id>` | `GET /findings/{id}` | One finding: Observed / Inference / Migration / Impact / Priority / Review |
| `cryptiq review-queue` | `GET /review-queue` | Global review queue, server-filtered |
| `cryptiq review-update <review_id>` | `PATCH /review-items/{id}` | Move one review item through a valid workflow transition |
| `cryptiq demo` | all of the above | Submit + poll + summarise the pyca/cryptography acceptance scan |

Global option: `--api-url` (or `$CRYPTIQ_API_URL`, default
`http://localhost:8000/api/v1`). Every command takes `--json`.

`findings` options: `--page`, `--page-size`, `--priority`, `--algorithm`,
`--role`, `--status` (review status), `--confidence`. All are forwarded to the
server as query parameters — nothing is filtered locally.

`review-queue` options: `--page`, `--page-size`, `--priority`, `--algorithm`,
`--role`, `--status`.

### Note on the review-queue `scan` filter

STEP 7 lists `scan` as a review-queue filter. The actual endpoint
(`app/api/v1/review_queue.py`) accepts only `priority`, `algorithm`, `role`,
`status` (and pagination) — there is no `scan` parameter. To honour the
"use the existing contract, do not filter locally" boundary, the CLI exposes
only the filters the API implements. To narrow the queue to one scan, use
`cryptiq findings <scan_id> --status open` instead.

## Missing commands

After this phase: none of the required set. Not implemented, and deliberately
out of scope for this phase (STEP 18):

- Gemini / LLM explanation commands (`GET /findings/{id}/explanation` exists
  but returns a deterministic placeholder until Gemini lands).
- Any command that mutates analysis data (findings are read-only from the CLI;
  only review items can be updated, through the existing PATCH).

## Files changed

New:

- `cryptiq/app/cli/__init__.py`
- `cryptiq/app/cli/__main__.py` — `python -m app.cli`
- `cryptiq/app/cli/client.py` — `CryptiqClient`, `CliError`, exit codes
- `cryptiq/app/cli/render.py` — tables, truncation, finding-detail view
- `cryptiq/app/cli/main.py` — argparse parser, command handlers, `main()`
- `cryptiq/tests/unit/test_cli.py` — 25 tests, `httpx.MockTransport` fake API
- `CLI_AUDIT.md` (this file)
- `DEMO_RUNBOOK.md`

Modified:

- `cryptiq/pyproject.toml` — added `cryptiq = "app.cli.main:main"` console script
- `cryptiq/README.md` — CLI section, demo flow

No analysis code, schema, migration, or existing endpoint was touched.

## Test strategy

- **Unit tests** (`tests/unit/test_cli.py`): stand up a fake `/api/v1` with
  `httpx.MockTransport`, inject it via `main(argv, client_factory=...)`, and
  assert on printed output + exit code. No network, no DB, no GitHub.
- Coverage: scan submission, cached scan, scan status (completed / failed /
  not-found), findings pagination + filters + JSON, finding detail (all
  blocks, `N/A` for nulls, not-found), review queue (list / filters / JSON),
  review update (partial body / usage error / invalid transition), demo
  (poll-to-completion / cache reuse / failure), transport failure, argument
  validation, and every exit code (0/1/2/3/4).
- **Real acceptance** (STEP 13): run manually against a live backend with the
  `pyca/cryptography @ 1f903f5…` commit. Documented in `DEMO_RUNBOOK.md`.
