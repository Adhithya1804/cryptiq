# Frontend Integration Audit — Cryptiq UI & FastAPI Backend

Date: 2026-09-10  
Workspace: `/Users/aadhi/cryptiq-2`  
Frontend: `frontend/` (React 18, TypeScript Strict, Vite 5, React Router 6)  
Backend: `cryptiq/` (FastAPI, SQLAlchemy 2.0, SQLite/PostgreSQL, Alembic)

---

## 1. Existing Screens

The frontend UI is an engineered implementation of `Cryptiq.dc.html` preserved in `frontend/src/pages/` with consistent layout, typography, and dark theme design tokens:

| Screen | Route | Component File | Description & State |
|---|---|---|---|
| **Analyze / Inspect** | `/inspect` (and `/`) | `pages/Inspect/InspectPage.tsx` | Repository URL & Commit SHA input form, validation, submission button, error banner, and assurance list. |
| **Inspection Report** | `/history/:inspectionId` | `pages/InspectionReport/InspectionReportPage.tsx` | Hero header, summary metrics bar, filter search bar, sortable findings table, live polling for async scans. |
| **Finding Detail** | `/findings/:findingId` | `pages/FindingDetail/FindingDetailPage.tsx` | Deep analysis hero screen: Observed facts (file, line range, commit, verbatim source excerpt), Inferred assessment (role, confidence, rationale), Migration review guidance (PQC candidate, target paths), Impact chain, Priority badge, Review action bar, and optional AI explanation panel. |
| **Review Queue** | `/review` | `pages/Review/ReviewPage.tsx` | Tabs for Active, Open, In Review, Completed; cards showing algorithm, role, reasons, recommended review path chips, reviewer assignment, relative age, priority color-coding. |
| **History** | `/history` | `pages/History/HistoryPage.tsx` | Historical list of all inspections, status dots, commit hashes, timestamps, findings count, severity clusters. |
| **Projects** | `/projects` | `pages/Projects/ProjectsPage.tsx` | Repositories known to Cryptiq with latest status, inspection dates, and finding counts. |
| **Project Detail** | `/projects/:projectId` | `pages/ProjectDetail/ProjectDetailPage.tsx` | Single project overview, severity cards, latest scan metrics, inspection history. |
| **Settings** | `/settings/:section` | `pages/Settings/SettingsPage.tsx` | 10 configuration sections (Workspace, Analysis, Crypto, Integrations, Access, Notifications, Audit, Security, Appearance, Danger). |
| **404 Not Found** | `*` | `pages/NotFound/NotFoundPage.tsx` | Empty state view with navigation back to Inspect. |

---

## 2. Existing Mock Data

- **API Layer**: There is **no hardcoded fake findings data** in the production flow. The application uses `assertBackendConfigured()` and `isBackendConfigured()`:
  - When `VITE_API_BASE_URL` is configured, all screens read from the API via `src/services/`.
  - When `VITE_API_BASE_URL` is empty, read screens render explicit clean empty states (`EmptyState`) and the scan submission surfaces a connection error banner.
- **Static Display Fixtures**:
  - `ASSURANCES` in `InspectPage.tsx`: Static assurance statements ("Static inspection", "Exact commit", "Repository code is never executed").
  - `SEV_ROWS` in `ProjectDetailPage.tsx`: Static configuration for the 4 severity cards (Critical, High, Medium, Low).
  - `TABS` in `ReviewPage.tsx`: Static tabs (`active`, `open`, `in_review`, `completed`).
  - `ACTION_STATUS` and `ACTION_TOAST` in `FindingDetailPage.tsx`: Disposition action labels and toast notification mappings.
  - `SettingsPage`: Default settings preferences stored in local storage.
- **Mock / Fixture Files for Tests**:
  - `src/services/http.test.ts`, `src/services/mappers.test.ts`, `src/services/services.test.ts`: Contain synthetic HTTP responses and test DTO fixtures used purely in automated unit tests.

---

## 3. Existing Expected Data Structures

The frontend consumes domain models via `src/types/domain.ts`, mapped from wire DTOs in `src/types/api.ts`:

- **Inspection / Scan (`Inspection` / `ApiInspectionDto`)**:
  - `id`: string (UUID)
  - `repositoryName`: string (`owner/name`)
  - `commitSha`: string (40-char SHA)
  - `status`: `'queued' | 'running' | 'completed' | 'failed' | 'cancelled'`
  - `startedAt`, `completedAt`: ISO string
  - `durationMs`: number | null
  - `filesAnalyzed`: number | null
  - `findingsCount`: number
  - `severity`: `{ critical: number, high: number, medium: number, low: number }`

- **Finding Summary (`FindingSummary` / `ApiFindingSummaryDto`)**:
  - `id`: string
  - `inspectionId`: string
  - `algorithm`: string (e.g. `'RSA'`, `'ECDSA'`, `'AES'`)
  - `api`: string (e.g. `'RSAPrivateKey.sign'`)
  - `role`: Cryptographic role (`'digital_signature'`, `'key_establishment'`, `'symmetric_encryption'`, `'hash'`, `'protocol'`, `'unknown'`)
  - `confidence`: `'high' | 'medium' | 'low' | 'unknown'`
  - `filePath`: string
  - `lineStart`: number, `lineEnd`: number | null
  - `priority`: `'critical' | 'high' | 'medium' | 'low' | 'informational'`
  - `reviewStatus`: `'open' | 'in_review' | 'resolved' | 'accepted_risk' | 'false_positive' | null`

- **Finding Detail (`Finding` / `ApiFindingDto`)**:
  - `observed`: `{ algorithm, api, filePath, lineStart, lineEnd, commitSha, repositoryName, language, source: [{ number, text, highlighted }] }`
  - `inferred`: `{ role, confidence, reasons: string[] }`
  - `migration`: `{ current, path: string[], summary, isMigrationCandidate: boolean }`
  - `impact`: `{ scope: 'statically_observed', chain: string[] }`
  - `priority`: `'critical' | 'high' | 'medium' | 'low'`
  - `review`: `{ id, status, assignee, note, updatedAt } | null`
  - `aiExplanationAvailable`: boolean

- **Review Queue Item (`ReviewQueueItem` / `ApiReviewQueueItemDto`)**:
  - `reviewId`: string
  - `findingId`: string
  - `inspectionId`: string
  - `priority`: FindingPriority
  - `algorithm`: string
  - `role`: CryptographicRole
  - `reviewPath`: string[]
  - `status`: FindingReviewStatus
  - `assignee`: string | null
  - `reasons`: string[]
  - `filePath`: string
  - `lineStart`: number
  - `updatedAt`: string | null

---

## 4. Existing Interactions

1. **Submit Scan**: User enters GitHub URL + 40-char SHA on `/inspect` → Clicks "Inspect Repository" → Submits payload → Navigates to `/history/:inspectionId`.
2. **Scan Polling**: On `/history/:inspectionId`, if scan is `queued` or `running`, polls every 2.5s via `useAsyncResource.refresh()` until `completed` or `failed`.
3. **Filter & Sort Findings**: In `/history/:inspectionId`, text search filters by algorithm, role, or file. Column headers sort by priority, algorithm, confidence. (Currently client-side on full result set).
4. **View Finding Detail**: Clicking a row opens `/findings/:findingId?from=report&inspection=:id` with verbatim source code, line numbers, epistemic separation.
5. **Review Queue Navigation & Tabs**: Navigating to `/review` loads queue items; clicking tabs filters by Active, Open, In Review, Completed.
6. **Review Disposition Action**: On `/findings/:findingId` or `/review`:
   - Start Review (`OPEN` → `IN_REVIEW`)
   - Mark Resolved / Accept Risk / False Positive (`IN_REVIEW` → `RESOLVED` / `ACCEPTED_RISK` / `FALSE_POSITIVE`)
   - Submits disposition and shows toast notification.


---

## 5. API Mismatches Found — and How They Were Resolved

The first integration wired the finished frontend to the backend on the
`/api/v1/inspections` routes with no pagination. This phase added the canonical
`/api/v1/scans` surface, server-side pagination and filtering, and the
id-keyed review PATCH, **without removing the `/inspections` routes** (all 699
prior backend tests still pass).

| Area | Contract | Before | Resolution |
|---|---|---|---|
| **Scan endpoints** | `POST /api/v1/scans`, `GET /api/v1/scans/{id}`, `GET /api/v1/scans/{id}/findings` | only `/api/v1/inspections` | Added `app/api/v1/scans.py`. Same entity as an inspection; `/inspections` kept. |
| **Submit response** | `202` queued, or `200` + `cached: true` | `201` + `ApiInspectionDto` | `POST /scans` returns `202`, or `200` with `cached: true` when a completed scan with the same seven-part identity exists. `ApiInspectionDto` gained a `cached` field (default `false`). |
| **Findings pagination** | `?page=&page_size=` → `{ items, total, page, page_size, pages }` | all rows in one response | `GET /scans/{id}/findings` is paged via `scans.list_findings_page()`; `page_size` capped at 200. New `ApiPageEnvelope[T]`. Frontend `InspectionReportPage` has Previous/Next + "Page X of Y" controls. |
| **Server-side filtering** | `priority`, `algorithm`, `role`, `status`, `confidence` | filtered in JS over the full list | Filtering is done in SQL (`_finding_filters`). The report page's search box maps to the `algorithm` param (substring, case-insensitive) and resets to page 1. Unknown enum tokens → `422`. |
| **Review updates** | `PATCH /api/v1/review-items/{review_id}` `{ status, assigned_to, note }` | only `POST /findings/{id}/review` | Added `app/api/v1/review_items.py` + `reviews.update_review_item()`. Omitted fields are untouched; `null` clears `assigned_to`/`note`. `POST /findings/{id}/review` kept for the create-on-first-touch path. |
| **Review transitions** | `409 INVALID_REVIEW_TRANSITION` on an illegal move | 409 raised, but the backend's transition table permits every pair among the five statuses, so it is currently latent | Frontend handles a `409` with that code (shows the message, does not fake the change). No change to the backend state machine — tightening it would break `OPEN → RESOLVED`, which existing tests rely on. |
| **Base URL config** | env var, dev default `http://localhost:8000` | `VITE_API_BASE_URL` only, no default | `config.ts` also reads `NEXT_PUBLIC_API_URL`. Dev default lives in `frontend/.env.development.local` (`http://localhost:8000/api/v1`); blank still means "no backend connected". No production URL is hard-coded. |
| **CORS** | allow the dev origin, no wildcard-with-credentials | `:5173` only, methods `GET/POST/OPTIONS` | Added `:3000` to the default `cors_allow_origins`; added `PATCH` to `allow_methods`. `allow_credentials` stays `false`. |
| **Missing engine fields** | `evidence_basis`, `priority.score/reasons`, `impact.relationships` may be null/empty | — | Left as the backend returns them; the UI shows an unavailable/omitted state and never substitutes a value. |
| **"Explain with AI"** | not implemented this phase | — | Panel shows "AI explanation unavailable for this finding" when no Gemini key is set. The browser never calls Gemini. |

## 6. Changes Made

### Backend (`cryptiq/`)

- `app/api/v1/scans.py` **[new]** — `POST /scans` (202 / 200 cached), `GET /scans/{id}`, `GET /scans/{id}/findings` (paged + filtered).
- `app/api/v1/review_items.py` **[new]** — `PATCH /review-items/{review_id}`.
- `app/api/v1/router.py` — mount `scans` and `review_items`.
- `app/api/v1/review_queue.py` — optional `page`/`page_size` + `priority`/`algorithm`/`role`/`status` filters; unfiltered call still returns the whole queue.
- `app/services/scans.py` — `create_scan()` returns `(scan, cached)`; `create_inspection()` kept as a wrapper. New `list_findings_page()` / `list_review_queue_page()` + `_parse_enum` / `_finding_filters` helpers.
- `app/services/reviews.py` — `get_review_item()`, `update_review_item()`, `UNSET` sentinel, `_check_transition()`.
- `app/schemas/api.py` — `ApiPageEnvelope[T]`, `cached` on `ApiInspectionDto`, `UpdateReviewItemRequest`.
- `app/main.py` — `PATCH` added to CORS `allow_methods`.
- `app/config.py` — `:3000` added to the default CORS origins.
- `tests/integration/test_scans_api.py` **[new]** — 11 tests: 202/200-cached, `/scans` vs `/inspections` parity, 404, pagination metadata, each server-side filter, `422` on a bad enum, review-status filter, PATCH workflow + clear-assignee + 404 + 422, review-queue pagination.

### Frontend (`frontend/`)

- `src/services/client.ts` **[new]** — the one place that knows the canonical paths: `createScan`, `getScan`, `getFindings`, `getFinding`, `getReviewQueue`, `updateReviewItem`. Returns mapped domain types; raw `fetch` still only in `http.ts`.
- `src/services/config.ts` — also reads `NEXT_PUBLIC_API_URL`.
- `src/services/inspections.ts` — `submitInspection`/`fetchInspection` delegate to the client; new `submitScan` returns `{ inspection, cached }`.
- `src/services/review.ts` — `fetchReviewQueue` now pages through the client.
- `src/services/index.ts` — export the client functions and `submitScan`.
- `src/types/api.ts` — `ApiPageEnvelope<T>`, `cached?`, `UpdateReviewItemRequest`.
- `src/types/domain.ts` — `Page<T>`, `FindingFilters`, `SubmittedScan`. (Dead cursor-`Page` removed from `types/common.ts`.)
- `src/vite-env.d.ts` — declare `NEXT_PUBLIC_API_URL`.
- `src/pages/InspectionReport/InspectionReportPage.tsx` (+ `.module.css`) — server-side pagination + `algorithm` filter (debounced, resets to page 1), Previous/Next pager styled with the existing tokens, 2s poll while queued/running, findings load in their own `AsyncBoundary`.
- `src/pages/FindingDetail/FindingDetailPage.tsx` — disposition uses `updateReviewItem` (PATCH) when the finding already has a review row, falling back to `submitFindingReview`; a `409 INVALID_REVIEW_TRANSITION` is surfaced, not faked.
- `src/services/client.test.ts` **[new]** — 12 tests: payload/URL/query for every function, cached scan, pagination math, filter omission, nested finding mapping, PATCH field selection + null-clear, `409` code propagation, `404`/`422`.

`ReviewPage.tsx` was intentionally left loading the full queue client-side: it is
a small (~132-item) tabbed triage view, and forcing single-status server
pagination onto its Active/Completed composite tabs would be a UX regression.
The paginated client path exists and is covered; the page can adopt it later.

## 7. Verification

| Gate | Result |
|---|---|
| Backend `pytest` | **710 passed, 33 skipped** (was 699; +11) |
| Backend `ruff check .` | clean |
| Frontend `tsc -b` | clean |
| Frontend `eslint --max-warnings 0` | clean |
| Frontend `vitest run` | **55 passed** (was 43; +12) |
| Frontend `vite build` | ok |
| Live browser acceptance (Steps 20–23) | passed — see below |

Live run: backend on `:8000` with the in-process worker, frontend dev server on
`:5173` (`VITE_API_BASE_URL=http://localhost:8000/api/v1`). The persisted scan of
`pyca/cryptography @ 1f903f5ed2e5e316f345a927555e48535829d8de` (1,042 findings,
132 review items) is real output from the prior live run.

1. `/inspect` → submitted the acceptance repo + commit → `POST /scans` returned
   `200 cached: true` → landed on the completed report immediately, no re-scan.
2. Findings table: 1,042 total, "Page 1 of 21", Next → "Page 2 of 21"
   (`?page=2&page_size=50`).
3. Filter "RSA" → `?page=1&page_size=50&algorithm=RSA`, "34 findings", page reset
   to 1, pager hidden (single page). The stale `page=2&algorithm=RSA` request was
   aborted by `useAsyncResource`, as intended.
4. Opened a finding → observed (RSA, `rsa.generate_private_key`,
   `tests/hazmat/primitives/test_rsa.py`, line 181, commit), inferred
   (role UNKNOWN — the backend's honest value — confidence High), review path
   `MANUAL REVIEW` with its rationale, priority High, impact chain
   algorithm → API → function → class → module → file, verbatim source excerpt.
   "AI explanation unavailable for this finding."
5. Review queue rendered real persisted items. Opened one, moved it
   **Open → In Review** (`PATCH /review-items/{id}` → `IN_REVIEW`, toast) →
   **Mark Resolved** (`PATCH` → `RESOLVED`, toast). The Completed tab shows it as
   Resolved; an item assigned via `PATCH` earlier still shows its assignee —
   persisted.
6. Resubmit of the same repo + commit → `200 cached: true` again, straight to the
   report, no worker run.

Browser console over the whole session: no application errors (the
`net::ERR_ABORTED` entries are `useAsyncResource` cancelling superseded
requests).

## 8. Not Done / Out of Scope (unchanged)

Gemini, CLI, AWS, auth, deployment, Kubernetes, redesign, new crypto rules or
analysis engines. The backend transition table still permits every review-status
pair (so `409 INVALID_REVIEW_TRANSITION` is latent); `assigned_to` has no UI
control yet (only the API and the finding-detail flow set it); `evidence_basis`,
`priority.score`/`reasons` and `impact.relationships` remain honestly
null/empty and are shown as such.
