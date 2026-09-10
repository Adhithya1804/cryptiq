# Cryptiq — Docker

Reproducible containerization of the full Cryptiq stack for local demo and, later,
AWS. The deterministic analysis engine, findings, fingerprints, priority, PQC
mappings and evidence semantics are **unchanged** — this is packaging only.

---

## 1. Architecture map (audit result)

| Concern | What the codebase does | Container decision |
|---|---|---|
| Backend entrypoint | `app.main:app` (FastAPI app factory `create_app`), console script `cryptiq-api` | `uvicorn app.main:app --host 0.0.0.0 --port 8000` |
| Worker | In-process async loop started in the app lifespan, gated by `RUN_WORKER` (`app/worker.py`) | Kept in-process — `RUN_WORKER=true` in the one backend container. No separate worker service. |
| Python | `requires-python >=3.12`; verified on 3.12 | `python:3.12-slim-bookworm` |
| Dependencies | `pyproject.toml` ranges, no lock file, venv is `uv`-managed | New fully-pinned `cryptiq/requirements.txt` (exact verified versions) + `requirements-dev.txt` |
| DB | SQLAlchemy, generic types; SQLite locally, PostgreSQL fully supported (worker uses `FOR UPDATE SKIP LOCKED` on PG, `pool_pre_ping`, Alembic `render_as_batch`) | SQLite on a named volume by default; PostgreSQL via an override file |
| Migrations | Alembic, URL comes from app settings (`migrations/env.py`), head `f4a5b6c7d8e9` | `alembic upgrade head` runs in the container entrypoint before the server starts |
| Health | `GET /health` + unprefixed alias (liveness only) | Added `GET /health/ready` (liveness **+ `SELECT 1`**); Docker healthchecks use it |
| Frontend build | Vite 5 + TS, `npm run build` → `dist/`, `createBrowserRouter` | Multi-stage: `node:20-alpine` build → `nginxinc/nginx-unprivileged` serving `dist/` |
| Frontend API URL | `import.meta.env.VITE_API_BASE_URL`, **must be absolute** (`new URL(path, base)` in `services/http.ts`) | Baked at build time as a `--build-arg`; browser calls the backend's published URL directly |
| CORS | `CORSMiddleware`, origins from `CORS_ALLOW_ORIGINS` (comma-separated) | Set to the frontend origin in compose |
| CLI | `cryptiq` console script, httpx client of the running API | Ships in the backend image; run via `docker compose exec backend cryptiq ...` |
| Existing Docker / CI | none found | Created here |

```
                    ┌────────────────────────────┐
  browser  ───────► │ frontend  (nginx :8080)     │   static SPA, SPA-routing fallback
     │              └────────────────────────────┘
     │              ┌────────────────────────────┐
     └────────────► │ backend   (:8000)          │   FastAPI + in-process scan worker
        CORS        │  uvicorn + tini (PID 1)    │
                    │  alembic upgrade head       │
                    └─────────────┬──────────────┘
                                  ▼
                    ┌────────────────────────────┐
                    │ SQLite  (named volume)      │   default
                    │   — or —                    │
                    │ postgres:16  (override)     │   deployment-representative
                    └────────────────────────────┘
```
`nginx` also proxies `:8080/api/ → backend:8000` as a same-origin convenience for
`curl`/scripts; the SPA itself uses the absolute `VITE_API_BASE_URL`.

---

## 2. Quick start (demo — SQLite)

Prerequisites: Docker Desktop / Engine with Compose v2.

```bash
cd cryptiq-2
cp .env.example .env          # defaults work as-is; no secrets required
docker compose up --build -d
```

Then:

- Frontend: <http://localhost:8080>
- Backend API: <http://localhost:8000/api/v1/health/ready>
- API docs: <http://localhost:8000/docs>

Stop / clean up:

```bash
docker compose down           # stop, keep the database volume
docker compose down -v        # stop and delete the database volume
```

### Preseeding the cached acceptance scan (optional)

A `*.db` file is git-ignored, so a fresh clone starts with an empty database.
To demo the cached scan instantly, drop a prepared SQLite DB at
`deploy/seed/cryptiq.db` **before** the first `up`:

```bash
cp cryptiq/cryptiq.db deploy/seed/cryptiq.db   # if you have one locally
```

The entrypoint copies it into the volume once, on first boot only. Without a
seed, run one scan through the UI (`pyca/cryptography` @
`1f903f5ed2e5e316f345a927555e48535829d8de`) and every resubmit of the same
repo+commit is then served from cache (`"cached": true`).

---

## 3. PostgreSQL (deployment-representative)

```bash
cp .env.example .env
# edit POSTGRES_PASSWORD for anything beyond a laptop
docker compose -f docker-compose.yml -f docker-compose.postgres.yml up --build -d
```

Adds a `postgres:16-alpine` service (internal network only, not published),
points the backend at `postgresql+psycopg://…@db:5432/cryptiq`, and runs the
same `alembic upgrade head`. A fresh Postgres starts empty — no seed path — so
produce the cached acceptance scan by running it once.

Tear down: `docker compose -f docker-compose.yml -f docker-compose.postgres.yml down -v`

---

## 4. Environment variables

Single file: **`./.env`** (copy from `.env.example`). Used both for Compose
variable interpolation and as the backend container's `env_file`. Git-ignored,
never copied into an image.

| Variable | Default | Purpose | Secret |
|---|---|---|---|
| `BACKEND_HOST_PORT` | `8000` | Host port for direct API/CLI access (container port is always 8000) | no |
| `ENVIRONMENT` | `production` | Name only | no |
| `DATABASE_URL` | set per-service in compose | `sqlite:////data/cryptiq.db` (default) or `postgresql+psycopg://…` (override) | no |
| `CORS_ALLOW_ORIGINS` | `http://localhost:8080,http://127.0.0.1:8080` | Browser origins allowed to call the API | no |
| `RUN_WORKER` | `true` | Run the in-process scan worker in the backend container | no |
| `GITHUB_API_URL` | `https://api.github.com` | GitHub ingestion base | no |
| `GITHUB_TOKEN` | *(empty)* | Optional — higher rate limit / private repos | **yes** |
| `GITHUB_TIMEOUT_SECONDS` | `30` | | no |
| `MAX_ARCHIVE_BYTES` | `262144000` | Ingestion bound | no |
| `MAX_EXTRACTED_BYTES` | `524288000` | Ingestion bound | no |
| `MAX_FILES` | `20000` | Ingestion bound | no |
| `MAX_FILE_BYTES` | `5242880` | Ingestion bound | no |
| `SCAN_TIMEOUT_SECONDS` | `300` | Analysis bound | no |
| `GEMINI_API_KEY` | *(empty)* | Optional. Server-side only. Unset ⇒ `AI_EXPLANATION_UNAVAILABLE` (503) and every finding stays fully usable | **yes** |
| `GEMINI_MODEL` | `gemini-2.5-flash` | | no |
| `GEMINI_TIMEOUT_SECONDS` | `30` | | no |
| `GEMINI_MAX_OUTPUT_TOKENS` | `1500` | | no |
| `PARSER_VERSION` / `RULESET_VERSION` / `PQC_RULESET_VERSION` | `python-ast-1` / `0.3.0` / `0.2.0` | Deterministic engine stamps — change only with the engine | no |
| `POSTGRES_PASSWORD` | `cryptiq` | Postgres override only | **yes** |
| `VITE_API_BASE_URL` | *(build arg)* `http://localhost:${BACKEND_HOST_PORT}/api/v1` | Baked into the SPA bundle at build time. **Never a secret** — anything in the bundle is world-readable | no |

**Never commit** `GEMINI_API_KEY`, `GITHUB_TOKEN`, `POSTGRES_PASSWORD`, or cloud
credentials. The browser bundle contains no key of any kind (verified — see §8).

---

## 5. Services, ports, volumes

| Service | Image | Container port | Published | Restart |
|---|---|---|---|---|
| `frontend` | `cryptiq-frontend:local` (nginx-unprivileged) | 8080 | `8080` | `unless-stopped` |
| `backend` | `cryptiq-backend:local` (python:3.12-slim) | 8000 | `127.0.0.1:${BACKEND_HOST_PORT:-8000}` (loopback only) | `unless-stopped` |
| `db` *(postgres override)* | `postgres:16-alpine` | 5432 | **not published** (internal network) | `unless-stopped` |

| Volume | Used by | Contents |
|---|---|---|
| `cryptiq-data` | backend | SQLite database file (`/data/cryptiq.db`) |
| `cryptiq-pgdata` | db (override) | PostgreSQL data directory |
| `./deploy/seed` (bind, ro) | backend | Optional one-time SQLite seed at `/seed/cryptiq.db` |

---

## 6. Health checks

| Service | Check | Meaning |
|---|---|---|
| backend | `GET /health/ready` → 200 (process up **and** `SELECT 1` succeeds); 503 otherwise | readiness, not just liveness |
| frontend | `wget /healthz` (nginx `return 200`) | static server responding |
| db (override) | `pg_isready -U cryptiq -d cryptiq` | accepting connections |

Compose gates `frontend` on `backend: service_healthy`, and (override) `backend`
on `db: service_healthy`. `GET /health` (liveness-only) is unchanged for any
existing supervisor that probes it.

---

## 7. CLI / API inside the stack

```bash
docker compose exec backend cryptiq review-queue --json
docker compose exec backend cryptiq scan https://github.com/pyca/cryptography <sha>
curl http://localhost:8000/api/v1/health/ready
```

The engine never executes repository code — ingestion downloads an archive at an
exact commit, parses Python to an AST, and analyses statically. SSRF guards and
bounded extraction are unchanged.

---

## 8. Security controls

- **Non-root runtime**: backend uid 1001 (`cryptiq`), frontend uid 101 (`nginx`).
- **tini as PID 1** in the backend image → clean `SIGTERM` shutdown, no zombies.
- **No secrets in images**: `.dockerignore` excludes `.env*`, `*.db`, `.git`;
  `docker history` is clean; config is runtime-injected only.
  (`GPG_KEY` visible in the backend image env is the upstream Python base
  image's own signing key, not a Cryptiq secret.)
- **No key in the browser bundle**: verified — `grep -rE "AIza|GEMINI|GITHUB_TOKEN|sk-" dist/` finds nothing.
- **Backend published on loopback only** (`127.0.0.1`); Postgres not published at all.
- **No debug mode**: uvicorn without `--reload`, `server_tokens off` in nginx,
  `--no-server-header` on uvicorn.
- **Slim base**, no build toolchain in the runtime stage (multi-stage; wheels only).
- **Structured errors**: validation → `422 validation_error`, missing → `404 not_found`,
  AI-side failure → `503 AI_EXPLANATION_UNAVAILABLE`; no stack traces or secrets in responses.
- Local image scan: `trivy` / `dive` not installed on this host; not blocking. Run
  `trivy image cryptiq-backend:local` in CI when available.

---

## 9. Verified end-to-end (SQLite stack)

| Check | Result |
|---|---|
| `docker compose up --build` from a clean state | both services `healthy` |
| `alembic upgrade head` in entrypoint | runs, idempotent |
| One-time seed copy | `/seed/cryptiq.db` → `/data/cryptiq.db` on first boot only |
| Frontend loads, deep routes on refresh (`/inspect`,`/projects`,`/history`,`/review`,`/findings/:id`,`/settings/:section`) | all resolve to the SPA shell |
| Backend `GET /health/ready` | `200 {"database":"ok"}` |
| CORS from `http://localhost:8080` | allowed |
| Cached acceptance scan (`pyca/cryptography` @ `1f903f5ed2e5…`) | `cached:true`, **241 files, 1042 findings, 136 High, 906 Medium** |
| Findings list / finding detail / impact / evidence | render |
| Review queue + `PATCH /review-items/{id}` status change | works, reverts |
| Gemini unset | finding detail shows "AI explanation unavailable"; `POST …/explanation` → `503 AI_EXPLANATION_UNAVAILABLE`; deterministic finding untouched |
| CLI in container (`cryptiq review-queue --json`) | works |
| Backend stopped mid-session | frontend static still serves; proxy returns nginx 504 (no trace); recovers on `docker compose start backend` |
| Malformed request | `422 {"error":{"code":"validation_error"}}` |
| PostgreSQL override | `db` healthy, all 6+ migrations apply on PG, readiness `database:ok` |

### Regression suite (host, verified environment)

| Suite | Before | After |
|---|---|---|
| Backend `pytest` | 759 passed / 34 skipped | **825 passed / 34 skipped** (Docker `/health/ready`, then the AWS/demo-hardening suite) |
| `ruff check .` | clean | clean |
| Frontend `vitest` | 57 | **57** |
| `tsc -b --noEmit` | clean | clean |
| `eslint . --max-warnings 0` | clean | clean |
| `vite build` | ok | ok |

---

## 10. Troubleshooting

| Symptom | Cause / fix |
|---|---|
| `bind: address already in use` on 8000 | Something else (e.g. a local `uvicorn`) holds it. Set `BACKEND_HOST_PORT=8001` in `.env` and `docker compose up -d` (rebuild the frontend too, since the API URL is baked in: `docker compose build frontend`). |
| Frontend shows "Could not reach the Cryptiq service" | The bundle's `VITE_API_BASE_URL` must be an **absolute** URL reachable from the browser and match the published backend port; `CORS_ALLOW_ORIGINS` must include the frontend origin. Rebuild `frontend` after changing either. |
| History/Review empty | Expected on a fresh DB with no seed — run a scan once. |
| `alembic` errors on start | Check `DATABASE_URL`; for Postgres ensure the `db` service is healthy first (the override wires `depends_on: service_healthy`). |
| Seed not applied | It copies **only** when `/data/cryptiq.db` does not yet exist. `docker compose down -v` to reset the volume. |
| AI explanation always 503 | `GEMINI_API_KEY` unset — this is the correct, safe default, not a bug. |

---

## 11. Limitations / not done (by design)

- No Kubernetes, Redis, Kafka, Celery, Terraform, or AWS resources — out of scope.
- No image vulnerability scan run here (`trivy` absent on the build host); wire it into CI.
- The cached acceptance scan is only auto-present when a `deploy/seed/cryptiq.db`
  is supplied; a pristine clone has none (DB files are git-ignored).
- Frontend API base URL is build-time (baked into the bundle), so a change of
  backend origin requires a `frontend` image rebuild. Acceptable for a demo /
  single-domain deployment; a runtime-config indirection can come with the AWS work.
- `docker compose down -v` deletes the database volume — the demo DB is disposable.
