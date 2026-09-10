# Cryptiq — Frontend/Backend Integration Report

Date: 2026-09-09

## 1. Repository audit

**Frontend (`frontend/`)** — React 18 + TypeScript (strict), react-router 6,
lazy routes. One HTTP boundary (`src/services/http.ts`): base-URL join, JSON,
timeout, abort propagation, `HttpError` normalisation. Wire types
(`src/types/api.ts`) → `src/services/mappers.ts` → domain types
(`src/types/domain.ts`); components never see raw responses. Data loaded through
one primitive, `useAsyncResource` (abort-on-unmount, stale-response rejection).
"No backend connected" mode when `VITE_API_BASE_URL` is unset. Baseline was
green: typecheck, lint, 38 tests, production build.

**Backend (`cryptiq/`)** — FastAPI + SQLAlchemy + Alembic. The deterministic
engine was complete: ingestion (SSRF-guarded GitHub archive fetch), Python AST
parser, crypto rules (RSA/AES/ECDSA/ECDH/Ed25519/X25519/hashes), role
classifier, PQC review-path mapper, bounded impact, priority scorer,
fingerprints. All 9 domain models + migrations existed. In-memory serialisers
(`app/services/findings.py`) already produced the canonical grouped finding.
**What did not exist:** any HTTP route beyond `GET /health`, any write path
from the engine to the database, the worker loop, explanation generation, and
CORS. Baseline: 685 tests passing.

So "integration" required building the backend's entire API + persistence +
worker layer to the shapes the finished frontend already expects.

## 2. Contract — every integrated endpoint

All under `/api/v1`. Collections return `{ items, total }`.

| Method | Path | Request | Response | Frontend consumer |
|---|---|---|---|---|
| POST | `/inspections` | `{ repository_url, commit_sha }` | `ApiInspectionDto` (201) | Inspect page |
| GET | `/inspections` | – | `{ items: ApiInspectionDto[] }` | History |
| GET | `/inspections/{id}` | – | `ApiInspectionDto` | Inspection report (polled while running) |
| GET | `/inspections/{id}/findings` | – | `{ items: ApiFindingSummaryDto[] }` | Inspection report table |
| GET | `/findings/{id}` | – | `ApiFindingDto` | Finding detail |
| GET | `/findings/{id}/explanation` | – | `ApiExplanationDto` | Finding detail AI panel |
| POST | `/findings/{id}/review` | `{ status, note? }` | `ApiReviewBlock` | Disposition bar |
| GET | `/review-queue` | – | `{ items: ApiReviewQueueItemDto[] }` | Review |
| GET | `/projects` | – | `{ items: ApiRepositoryDto[] }` | Projects |
| GET | `/projects/{id}` | – | `ApiRepositoryDto` | Project detail |
| GET | `/projects/{id}/inspections` | – | `{ items: ApiInspectionDto[] }` | Project detail |

Full field-level shapes, enums, nullability and error contract are in
`cryptiq/FRONTEND_BACKEND_CONTRACT.md` (rewritten to describe the implemented
contract).

## 3. Changes

### Backend — new
- `app/schemas/api.py` — wire DTOs mirroring `frontend/src/types/api.ts`.
- `app/services/persistence.py` — engine `AnalysisResult` → `Finding` /
  `Evidence` / `ImpactNode` rows; dedup by fingerprint within a scan;
  auto-open a `ReviewItem` for every migration candidate.
- `app/services/scans.py` — create inspection (repo upsert, cache reuse,
  `Scan` + `ScanJob`), reads for scans/findings/projects/review-queue.
- `app/services/reviews.py` — disposition with transition checking.
- `app/services/serialize.py` — rows → wire DTOs; recomputes only the PQC
  review path (pure lookup on stored algorithm + role).
- `app/worker.py` — in-process async worker loop: claim job → RUNNING →
  ingest + analyse (engine in a threadpool) → persist → COMPLETED, with
  bounded retry then FAILED and safe error codes.
- `app/integrations/gemini/` + `app/services/explanations.py` — server-side
  explanation generation, cached per finding, non-fatal on failure.
- `app/api/v1/{inspections,findings,projects,review_queue}.py` — routers.
- 3 migrations: widen `ReviewStatus` to the four dispositions; make
  `impact_nodes.relationship` nullable (engine root node); add
  `priority_score` / `priority_reasons` / `role_rationale` to `findings`.
- 5 test files (14 tests): full HTTP flow, worker failure path, explanation
  success/failure/cache, persistence dedup + pre-queue.

### Backend — modified
- `app/main.py` — CORS middleware + worker lifespan.
- `app/config.py` — `cors_allow_origins`, `run_worker`, `cors_origins`.
- `app/api/v1/router.py` — mount the new routers.
- `app/db/models/enums.py`, `finding.py`, `impact_node.py` — as above.
- `.env.example`, `FRONTEND_BACKEND_CONTRACT.md`.

### Frontend — modified (integration glue only, no redesign)
- `src/services/http.ts` + `src/types/api.ts` — read Cryptiq's
  `{ error: { code, message } }` envelope (still accepts the flat shape).
- `src/hooks/useAsyncResource.ts` — add `refresh()` (background reload, keeps
  current data, swallows a failed poll). Additive; `reload()` unchanged.
- `src/pages/InspectionReport/InspectionReportPage.tsx` — poll
  `GET /inspections/{id}` every 2.5 s via `refresh()` while status is
  queued/running; stop on any terminal state; torn down on unmount.
- `src/services/http.test.ts` — new (5 tests).

## 4. Contract mismatches found and resolved

| Mismatch | Resolution |
|---|---|
| Backend had no API; frontend expected 11 endpoints | Built the endpoints to the frontend's existing wire shapes (its `api.ts` is the de-facto spec). |
| "scan" (backend) vs "inspection" (frontend) | One entity; `/inspections` serialises a `Scan`. Documented. |
| `ApiInspectionDto` wants `severity {c/h/m/l}`, `duration_ms`, `files_analyzed`; `ScanRead` had none | New DTO; severity via one grouped query; duration from timestamps. Engine emits no CRITICAL — bucket stays 0. |
| `review.status`: backend `OPEN/IN_REVIEW/REVIEWED` vs frontend 5-state | Widened `ReviewStatus` enum to `OPEN, IN_REVIEW, RESOLVED, ACCEPTED_RISK, FALSE_POSITIVE` (migration `c1d2e3f4a5b6`); `REVIEWED` kept as a legacy alias for `RESOLVED`. |
| Error body `{error:{code,message}}` vs frontend reading top-level `message`/`code` | Extended `http.ts` normaliser to read the nested envelope. Backend error contract and its tests unchanged. |
| `finding.id` = fingerprint (not globally unique across scans) | Persisted API uses the `Finding` row UUID; the engine-level helper still returns the fingerprint. Documented. |
| Engine emits 2 matches with 1 fingerprint (line-independent) → `UNIQUE(scan_id, fingerprint)` violation (**found by the real E2E**) | `persist_analysis` folds duplicates into the first occurrence; `findings_count` counts distinct logical findings. |
| `priority.score` / `reasons` / role rationale needed by API, not persisted | Added three columns to `findings` (migration `e3f4a5b6c7d8`) — the minimal change to expose existing engine output. |
| Frontend had no polling; backend scans are async | Added background polling to the report page only. |
| `GEMINI_API_KEY=` (empty string) read as configured | `ai_explanation_available = bool(key)`. |

## 5. Scan flow (frontend → API → worker → analysis → DB → API → frontend)

```
Inspect form → POST /api/v1/inspections { repository_url, commit_sha }
  → parse_repository_url, normalize SHA, upsert Repository
  → if a COMPLETED scan with the same 7-part identity exists, return it
  → else Scan(QUEUED) + ScanJob(QUEUED); 201 ApiInspectionDto
frontend navigates to /history/{id}, polls GET /inspections/{id} every 2.5s
worker loop (in-process, RUN_WORKER=true):
  claim ScanJob (QUEUED→RUNNING), Scan→RUNNING, started_at
  ingest_commit (GitHub zip, SSRF allowlist) → analyze_snapshot (threadpool)
  persist_analysis: Finding+Evidence+ImpactNode rows, dedup by fingerprint,
    OPEN ReviewItem per migration candidate, scan counts
  ScanJob→COMPLETED, Scan→COMPLETED, completed_at
  on error: retry (max 3) then ScanJob→FAILED, Scan→FAILED + safe error_code
frontend poll sees COMPLETED → renders report + GET /inspections/{id}/findings
```

## 6. Review flow (frontend → API → DB → frontend)

```
ReviewActionBar → POST /api/v1/findings/{id}/review { status, note? }
  → parse_status (REVIEWED→RESOLVED alias; unknown → 422)
  → load Finding, take/create its ReviewItem
  → check transition (bad → 409 INVALID_REVIEW_TRANSITION)
  → set status/note, commit
  → 200 ApiReviewBlock (authoritative)
frontend applies the returned status; on failure it surfaces the error and
keeps the authoritative state. A reload re-reads GET /findings/{id} and
GET /review-queue.
```

## 7. Gemini flow (frontend → backend → Gemini → backend → frontend)

```
AiExplanation panel (only if ai_explanation_available) → GET /findings/{id}/explanation
  → ExplanationService: return a cached COMPLETED Explanation if present
  → else Explanation(PENDING); build a prompt from the finding's deterministic
    facts; GeminiClient.generate (key as query param to the official host,
    never logged, hard timeout)
  → COMPLETED + summary, or FAILED → 502 EXPLANATION_FAILED
frontend shows the summary, or an inline error + retry; the finding is
unaffected either way. Browser never contacts Gemini.
```

## 8. Test results

| Gate | Result |
|---|---|
| Frontend `tsc -b --noEmit` | pass |
| Frontend `eslint . --max-warnings 0` | pass |
| Frontend `vitest run` | 43 passed (was 38; +5 `http.test.ts`) |
| Frontend `vite build` | pass |
| Backend `pytest` | 699 passed, 33 skipped (was 685; +14) |
| Backend `ruff check` | pass |
| Backend `alembic upgrade head` | pass (3 new migrations) |
| Real end-to-end | see §9 |

## 9. Real end-to-end (browser-driven, live servers, real GitHub)

Backend on `:8000` (SQLite, worker on), frontend dev server on `:5173` with
`VITE_API_BASE_URL=http://localhost:8000/api/v1`.

1. Inspect page → submitted `https://github.com/pyca/cryptography` @
   `1f903f5ed2e5e316f345a927555e48535829d8de` → navigated to `/history/{id}`,
   status **Running**, no invented progress.
2. Worker downloaded the archive, analysed it, persisted. Real result:
   **status COMPLETED, 241 files, 1042 findings, 136 HIGH / 906 MEDIUM**,
   duration 4m 39s. The report page picked it up by polling (no reload).
3. Findings table rendered all 1042 rows from the backend.
4. Opened a finding: real source excerpt (plain text), observed block (ECDSA,
   `ECDSA.verify`, file, lines, commit) visually separate from the inferred
   block (DIGITAL_SIGNATURE, High), impact chain from persisted nodes,
   review path `ML-DSA / SLH-DSA` with the FIPS-204/205 rationale, priority
   High, status Open (auto-queued).
5. Review queue: 132 migration candidates, ordered by priority score, each
   with its priority reasons and review-path chip.
6. Disposition: Open → **Start Review** (toast, status In Review) → **Mark
   Resolved** (toast, "removed from active queue"). Hard-navigated to
   `/review?tab=completed` → the finding shows **Resolved** — persisted.
7. Deep link: cold-loaded `/findings/{uuid}` directly → full finding
   reconstructed from the backend.
8. `ai_explanation_available` is false (no key) → panel shows "AI explanation
   unavailable"; the rest of the finding is intact.
9. Stopped the backend → History shows "CONNECTION ERROR … Try again", no
   crash, no fake data. Restarted → "Try again" recovered the real data.
10. Projects and Project-detail pages render the real repository, latest
    status, and severity breakdown.

Browser console over the whole session: only Vite HMR socket noise and the
`ERR_CONNECTION_REFUSED` from the deliberate backend-down step. No application
errors.

## 10. Remaining issues / not verified

- **Pagination** is not implemented; the findings list and review queue return
  everything (~1042 rows rendered client-side on the acceptance commit). The
  `ApiListEnvelope` already carries `total`/`next_cursor` for when it lands.
- **`assigned_to`** is never set by any endpoint (UI shows "Unassigned").
- **Explanation** exposes only `summary`; `what_it_means` / `why_it_matters` /
  `review_action` are stored but unused.
- **`SCAN_TIMEOUT_SECONDS`** is not enforced by the worker.
- **Live Gemini** was not exercised end to end (no API key available). The
  service, client, caching, and the failure path are covered by tests with a
  stubbed client; the "unavailable" state was verified in the browser.
- **Multi-worker / Postgres** claim safety (`FOR UPDATE SKIP LOCKED`) is coded
  but only the single-worker SQLite path was run.
- The GitHub archive temp file (`cryptiq-archive-*.zip`) is left in the system
  temp dir after a scan — pre-existing `GitHubSourceProvider` behaviour, not
  changed here.

## 11. Out of scope

- **Docker / Docker Compose: NOT IMPLEMENTED.**
- **Deployment / AWS / CI-CD: NOT IMPLEMENTED.**
- **Phases 13–16: NOT IMPLEMENTED.**
