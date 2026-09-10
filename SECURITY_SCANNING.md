# Security scanning in CI

Cryptiq's Docker images are verified structurally (non-root runtime, no secrets
in layers, no `.env` files, minimal runtime images, multi-stage builds — see
[`DOCKER.md`](DOCKER.md) §8). What could not be done on the build host was
**image vulnerability scanning**. CI does it now, with Trivy, against the exact
images the CI build produces.

Defined in [`.github/workflows/ci.yml`](.github/workflows/ci.yml). Verified with
Trivy **0.74.0**.

## Repository layout this expects

The workflow assumes one tree:

```
<repo root>/
├── .github/workflows/ci.yml
├── trivy.yaml
├── .trivyignore.yaml
├── .github/scripts/findings_to_sarif.py
├── docker-compose.yml  docker-compose.postgres.yml
├── cryptiq/     FastAPI backend + CLI + cryptiq/Dockerfile
└── frontend/    React/Vite + frontend/Dockerfile
```

Every path in the workflow (`context: ./cryptiq`, `working-directory: frontend`,
`cache-dependency-path: cryptiq/requirements-dev.txt`, …) is relative to that
root. If the backend and frontend live in **separate** repositories, this single
workflow does not apply unchanged: split it into one workflow per repo, or add a
second `actions/checkout` with `repository:` + `path:` to assemble the tree.

## Pipeline

```
Pull request / push
   │
   ├── backend-quality      ruff · pytest            (baseline 825 passed / 34 skipped)
   ├── frontend-quality     tsc · eslint · vitest · vite build   (baseline 57 passed)
   │
   ├── docker-build         builds cryptiq-backend + cryptiq-frontend
   │   (needs both quality) exports each as a docker-archive tar artifact (no registry push)
   │
   ├── trivy-scan  (matrix: backend, frontend; needs docker-build)
   │      ├── ONE authoritative scan of the EXACT built image
   │      │      trivy image --input <tar> --config trivy.yaml
   │      │      --scanners vuln,secret,misconfig --show-suppressed --format json
   │      ├── report  HIGH + CRITICAL           → job summary + trivy-<img>-high.txt
   │      ├── report  all severities + suppressed → trivy-<img>-all.txt  (base-image CVEs visible)
   │      ├── build-context  trivy fs secret,misconfig → trivy-<img>-context.txt
   │      ├── SARIF  HIGH + CRITICAL            → GitHub code scanning (category trivy-<img>)
   │      ├── artifacts: JSON + SARIF + all three text reports
   │      └── GATE  trivy convert --exit-code 1 --severity CRITICAL   (secrets are CRITICAL too)
   │
   └── cryptiq-self-scan  (needs backend-quality)
          start backend+worker → CLI submit → bounded poll to COMPLETED
          → GET /scans/{id}/findings (all pages) → findings_to_sarif.py → SARIF 2.1.0
          → GitHub code scanning (category cryptiq-self-scan)
```

## Image vulnerability scanning — the contract

| Requirement | How it is met |
|---|---|
| Tool is Trivy | `aquasecurity/setup-trivy@v0.2.6`, `version: v${TRIVY_VERSION}` (pinned `0.74.0`). |
| Scan **both** images | `trivy-scan` matrix over `backend` and `frontend`. |
| **CRITICAL fails CI** | Gate step `trivy convert --exit-code 1 --severity CRITICAL`. |
| **HIGH is reported** | `trivy convert --severity HIGH,CRITICAL` table → job summary + `trivy-<img>-high.txt`. Exit 0. |
| **Base-image / unfixed vulnerabilities visible** | `trivy.yaml` sets `pkg.types: [os, library]` and `vulnerability.ignore-unfixed: false`; the scan runs `--show-suppressed`, and `trivy-<img>-all.txt` is `trivy convert --show-suppressed` over every severity, so even reviewed exceptions stay in the report marked *ignored*. |
| **Secrets / config leakage checked** | Image scan uses `--scanners vuln,secret,misconfig`. Trivy rates a hardcoded secret **CRITICAL**, so a leak also trips the gate. The build context is additionally scanned with `trivy fs --scanners secret,misconfig`. |
| **No suppression to go green** | The only suppression channel is [`.trivyignore.yaml`](.trivyignore.yaml). It holds only reviewed, time-boxed, *unfixable* base-image CRITICALs (see the register below); a CVE with an available fix may never be listed. |
| **Scan the exact CI-built images** | `docker-build` exports each image with `outputs: type=docker,dest=…tar`; `trivy-scan` downloads that artifact and runs `trivy image --input <tar>`. Same bytes, no rebuild. |
| **No registry push for scanning** | Nothing is pushed. Images move between jobs as `actions/upload-artifact` tarballs (retention 1 day). |
| **Raw report kept** | `trivy-<img>.json` (full, all severities, suppressed included) is uploaded as an artifact, retention 7 days. |

### One authoritative scan, then convert

Trivy runs **once** per image; every downstream view (HIGH table, all-severities
table, SARIF, the CRITICAL gate) is produced with `trivy convert` from that one
`trivy-<img>.json`, so the gate and the reports can never disagree. The gate
step does **not** pass `--show-suppressed`, so registered exceptions do not
count toward it; every other view does pass it, so they stay visible.

## `.trivyignore.yaml` — exception register

An entry is admissible only when **all** hold: (1) the package comes from the
base image, not Cryptiq code or a pinned dependency; (2) no fixed version exists
upstream (`will_not_fix` / `affected` / `fix_deferred`); (3) it is not
reachable/exploitable in Cryptiq's usage. Every entry carries a written
`statement` and an `expired_at` ≤ 90 days out. On expiry Trivy re-reports the
CVE and the gate fails until it is re-reviewed, re-dated, or fixed by a
base-image bump.

Current entries — reviewed **2026-09-10**, all from `python:3.12-slim-bookworm`
(backend runtime base), all OS packages with **no released fix**, re-review by
**2026-12-09**:

| CVE | Package | Upstream status | Why not reachable in Cryptiq |
|---|---|---|---|
| CVE-2023-45853 | zlib1g | Debian `will_not_fix` | Overflow is in zlib `contrib/minizip`, not built into Debian's `libz`. Cryptiq uses Python `zipfile` for bounded extraction, never MiniZip. |
| CVE-2025-7458 | libsqlite3-0 | Debian `affected`, no fix | Integer overflow needs crafted SQL with extreme values; Cryptiq's SQLite DB holds only its own analysis output and is never fed untrusted SQL. |
| CVE-2026-13221 | perl-base | Debian `affected`, no fix | Perl regex engine flaw; perl is never invoked by Cryptiq at build or run time. |
| CVE-2026-8376 | perl-base | Debian `affected`, no fix | Heap overflow compiling Perl regexes; perl never invoked. |
| CVE-2026-42496 | perl-base (Archive::Tar) | Debian `fix_deferred` | Path traversal in `Archive::Tar`; Cryptiq never runs perl or `Archive::Tar`. |

HIGH findings are reported, not gated, so they never belong here. CRITICALs in
Cryptiq's own code or dependencies must be **fixed**, never listed.

## Findings from the first scan that are NOT exceptions

`nginxinc/nginx-unprivileged:1.27-alpine` (frontend runtime base) carries
**CVE-2026-31789** (CRITICAL) in `libcrypto3` / `libssl3`, **status `fixed`**
in Alpine `3.3.7-r0`. Because a fix exists this is **not** eligible for
`.trivyignore.yaml`. Resolution: rebuild the frontend image on a refreshed base.

- `:1.27-alpine` is a mutable tag; a fresh CI build pulls the newest base, so
  once nginxinc republishes on patched OpenSSL the finding clears on its own.
- Until then the `trivy-scan` gate on the **frontend** image is **expected to
  fail** — this is the fail-closed behaviour the contract requires, not a CI
  bug. To make it reproducible, pin `frontend/Dockerfile` to a base **digest**
  known to include `libcrypto3 >= 3.3.7-r0`.

*(Counts are from a local scan of the two base images on 2026-09-10 with Trivy
0.74.0; the exact CI images could not be built here — Docker daemon
unavailable. Numbers on a real runner will differ as upstream bases move.)*

## Cryptiq self-scan (deterministic analysis + SARIF)

`cryptiq-self-scan`:

1. `pip install -r cryptiq/requirements.txt` — **Cryptiq's own dependencies
   only**. Nothing from the analysed tree is installed or executed.
2. `alembic upgrade head`, then `uvicorn app.main:app` on `127.0.0.1:8000` with
   `RUN_WORKER=true` (in-process scan worker) and `DATABASE_URL` = a throwaway
   SQLite file.
3. `python -m app.cli scan <server_url>/<repo> <sha> --json` → a scan `id`.
   `POST /scans` is **asynchronous**: it returns `202` + `status: QUEUED` (or
   `200` + `cached: true` for a repeat identity).
4. Bounded poll: `python -m app.cli scan-status <id> --json` every 5 s, up to
   120 tries (~10 min). `COMPLETED` → proceed; `FAILED` → `::error::` + dump
   `uvicorn.log`, exit 1; timeout → exit 1. No unbounded loop.
5. [`findings_to_sarif.py`](.github/scripts/findings_to_sarif.py) pages
   `GET /scans/{id}/findings?page=N&page_size=200` until `page >= pages`,
   collecting **every** finding, and writes SARIF 2.1.0.
6. `github/codeql-action/upload-sarif@v3`, category `cryptiq-self-scan`.

**The analysed repository is never executed.** Cryptiq downloads a source
archive for the exact commit (SSRF-guarded, size-bounded) and runs Python AST
analysis only. CI installs no target dependencies, runs no target build, no
`setup.py`, no `make`, no target tests.

- **Required:** the deterministic analysis and the SARIF upload.
- **Not required:** the Gemini explanation layer. `GEMINI_API_KEY` is left
  unset; `POST /…/explanation` returns `503 AI_EXPLANATION_UNAVAILABLE` and the
  deterministic result is unaffected. CI never sets a Gemini key.

### SARIF mapping (`findings_to_sarif.py`)

| SARIF | Source |
|---|---|
| `runs[0].tool.driver.name` | `Cryptiq` |
| `rules[].id` | `cryptiq/<algorithm>-<operation>` (lower-kebab), deduped, sorted |
| `results[].level` | `priority` → `critical`/`high` = **error**, `medium` = **warning**, `low`/`informational` = **note** |
| `results[].locations[0].physicalLocation.artifactLocation.uri` | finding `file_path`, already repository-relative, leading `./` stripped |
| `region.startLine` / `region.endLine` | finding `start_line` / `end_line` (falls back to `start_line`) |
| `partialFingerprints.cryptiqFindingId/v1` | finding `id` (stable across runs for the same commit identity) |
| `properties` | `priority_score`, `is_migration_candidate`, `review_status` |

No API key, token, DB credential, Gemini key, or source excerpt is emitted —
only algorithm/operation/role/priority metadata plus file + line. Verified by
grep over generated SARIF.

## Exit-code semantics

| Situation | CI behaviour |
|---|---|
| Trivy finds no non-suppressed CRITICAL and no secret | gate step exits 0 → job passes |
| Trivy finds a CRITICAL / a leaked secret | gate step exits 1 → job fails |
| `cryptiq` CLI submits a scan successfully | step passes (CLI exit 0 on `202`/`200`) |
| Cryptiq scan reaches `COMPLETED` (with or without findings) | job passes — **findings are not a failure** |
| Cryptiq scan reaches `FAILED` | job fails, `status.json` + `uvicorn.log` dumped |
| Cryptiq scan never completes within ~10 min | job fails (timeout) |
| SARIF generation raises / SARIF is not 2.1.0 | step fails (explicit `assert`) |
| SARIF upload rejected by GitHub | `upload-sarif` step fails |

The CLI's own codes (`0` ok, `1` failure, `2` usage, `3` scan failed, `4` not
found — from `app/cli/client.py`) are preserved; the workflow keys off the JSON
`status` field, not a blanket `exit != 0`, so "Cryptiq found findings" is never
confused with "Cryptiq failed".

## Permissions & secrets

- Workflow default `permissions: contents: read`.
- `security-events: write` granted **only** to `trivy-scan` and
  `cryptiq-self-scan` (SARIF upload). No `contents: write`, no `packages:`, no
  `id-token:`.
- Only secret used: `GITHUB_TOKEN` (`${{ github.token }}`), passed to the
  backend so it can pull the commit archive without anonymous rate limits. It is
  never `echo`ed, never written to an artifact. `uvicorn.log` is uploaded but
  contains only request logs.
- `pull_request` runs from forks get a read-only token: SARIF upload will be
  skipped/denied by GitHub for fork PRs. Same-repo branches and `push` are
  unaffected.

## PR diff behaviour

The current `cryptiq` CLI has **no** base/head diff mode (`scan`, `scan-status`,
`findings`, `finding`, `review-queue`, `review-update`, `demo` only). The
self-scan therefore analyses the **whole** tree at `github.sha` and uploads all
findings to code scanning; GitHub itself diffs alerts between the PR head and
base and shows only newly-introduced ones in the PR. No engine change was made
to compute diffs, per the non-goals.

## Running it locally

```bash
# Backend quality
cd cryptiq && python -m ruff check . && python -m pytest -q

# Frontend quality
cd frontend && npm ci && npm run typecheck && npm run lint && npm test && npm run build

# Image scan (needs a Docker daemon + trivy on PATH)
docker build -t cryptiq-backend:local ./cryptiq
docker build -t cryptiq-frontend:local \
  --build-arg VITE_API_BASE_URL=http://localhost:8000/api/v1 ./frontend

trivy image --config trivy.yaml --scanners vuln,secret,misconfig --show-suppressed \
  --format json --output trivy-backend.json cryptiq-backend:local
trivy convert --severity HIGH,CRITICAL trivy-backend.json          # what CI reports
trivy convert --exit-code 1 --severity CRITICAL trivy-backend.json # what CI gates on

# Cryptiq self-scan (needs the backend running with RUN_WORKER=true)
cd cryptiq && CRYPTIQ_API_URL=http://127.0.0.1:8000/api/v1 \
  python -m app.cli scan https://github.com/<owner>/<repo> <full-sha> --json
python .github/scripts/findings_to_sarif.py \
  --api-url http://127.0.0.1:8000/api/v1 --scan-id <id> --repo-root . --output cryptiq.sarif
```

## Verification status

Validated locally on 2026-09-10:

- `actionlint` clean on `ci.yml`.
- Backend suite green (825 passed / 34 skipped, 0 failures); `ruff` clean.
- Frontend: `typecheck`, `lint` clean; `vitest` **57 passed**; `vite build` ok.
- `docker compose config` and the Postgres override both parse.
- Trivy 0.74.0 run against the real base images `python:3.12-slim-bookworm` and
  `nginxinc/nginx-unprivileged:1.27-alpine` with this `trivy.yaml`: scanners
  `vuln,secret,misconfig` all active, `pkg.types` accepted (no deprecation
  warning), gate correctly exits 1 on CRITICAL and 0 once the register is
  applied, expired register entries correctly reappear, `--show-suppressed`
  keeps excepted CVEs in the report.
- Trivy → SARIF (`--severity HIGH,CRITICAL`): valid 2.1.0.
- Live Cryptiq self-scan of `github.com/Invinciblx777/cryptiq`: `202 QUEUED`
  → poll → `COMPLETED` (156 files, 78 findings, 49 HIGH / 29 MEDIUM), CLI exit
  0; `findings_to_sarif.py` retrieved all 78 across 2 pages and produced valid
  SARIF 2.1.0 (49 `error`, 29 `warning`, 25 rules, repo-relative URIs, no
  secrets).

**Not yet done:** a real GitHub Actions run. There is no Git repository at the
tree root and no writable remote for this monorepo layout (`cryptiq/` is a
separate backend-only repo the CI author cannot push to; `frontend/` has no
commits). Publishing the full tree to a new repository to exercise Actions was
out of scope for this task. Until that run exists the pipeline status is
**YELLOW**.
