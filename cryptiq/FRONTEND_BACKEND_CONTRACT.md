# Cryptiq frontend/backend contract

## Status: implemented and integrated

Both sides are now readable and wired together. The React frontend
(`../frontend`) calls the FastAPI backend through one service layer
(`frontend/src/services/`); wire shapes are declared in
`frontend/src/types/api.ts`, mirrored on the backend by `app/schemas/api.py`,
and normalised onto `frontend/src/types/domain.ts` by `services/mappers.ts`.

Set `VITE_API_BASE_URL` to the backend's versioned root
(`http://localhost:8000/api/v1`) and the frontend makes real calls. With that
variable unset it runs in "no backend connected" mode: reads yield empty
collections, the inspection submit rejects with a connection error, and no
data is fabricated.

The backend is the single source of truth for analysis. The frontend never
computes an algorithm, role, confidence, review path, impact, priority,
fingerprint, or review decision.

## Vocabulary: "inspection" vs "scan"

The frontend screen and the backend domain use different words for the same
entity. A user submits an **inspection**; the backend stores it as a
**Scan** with a claimable **ScanJob**. The `/inspections` routes serialise a
`Scan` row into the `ApiInspectionDto` shape. There is one entity.

## Endpoints

All under `/api/v1`. Every collection response is `{ items: [...], total }`.

| Method | Path | Request | Response | Frontend consumer |
|---|---|---|---|---|
| `GET` | `/health` | – | `{ status, service, version }` | – |
| `POST` | `/inspections` | `{ repository_url, commit_sha }` | `ApiInspectionDto` (201) | Inspect page → navigates to `/history/:id` |
| `GET` | `/inspections` | – | `{ items: ApiInspectionDto[] }` | History |
| `GET` | `/inspections/{id}` | – | `ApiInspectionDto` | Inspection report (polled while queued/running) |
| `GET` | `/inspections/{id}/findings` | – | `{ items: ApiFindingSummaryDto[] }` | Inspection report table |
| `GET` | `/findings/{id}` | – | `ApiFindingDto` | Finding detail |
| `GET` | `/findings/{id}/explanation` | – | `ApiExplanationDto` | Finding detail (AI panel) |
| `POST` | `/findings/{id}/review` | `{ status, note? }` | `ApiReviewBlock` | Finding detail disposition bar |
| `GET` | `/review-queue` | – | `{ items: ApiReviewQueueItemDto[] }` | Review |
| `GET` | `/projects` | – | `{ items: ApiRepositoryDto[] }` | Projects |
| `GET` | `/projects/{id}` | – | `ApiRepositoryDto` | Project detail |
| `GET` | `/projects/{id}/inspections` | – | `{ items: ApiInspectionDto[] }` | Project detail |

### Identifiers

* `inspection.id` — the `Scan` row UUID. The frontend route key for
  `/history/:id`.
* `finding.id` — the `Finding` row UUID (**not** the fingerprint). It is
  globally unique, so `/findings/{id}` needs no scan context. The fingerprint
  still identifies the same logical finding across commits and is what the
  engine-level `to_finding` helper returns; the persisted API uses the row id.
* One row per `(scan, fingerprint)`. The fingerprint deliberately excludes
  line numbers, so the engine can emit two matches with one fingerprint (the
  same construct used twice in a function). Persistence keeps the first in the
  engine's deterministic order and folds the rest into it; `findings_count` is
  the number of distinct logical findings, which is why it can be lower than
  the raw match count.
* `review.id` — the `ReviewItem` row UUID.

## Wire shapes

`ApiInspectionDto`

```
id, repository_id, repository { provider, owner, name, url },
language ("Python"), commit_sha, status,
started_at, completed_at, duration_ms, files_analyzed,
findings_count, severity { critical, high, medium, low },
error_code, error_message
```

`ApiFindingDto` — grouped by how far a reviewer can trust each part.

```
id, scan_id, repository, commit_sha, language,
observed  { rule_id, algorithm, api, primitive, library, operation,
            location { file_path, start_line, end_line,
                       start_column, end_column },
            source_excerpt, parser_version, ruleset_version },
inference { role, rationale: string[], confidence, evidence_basis? },
migration { review_path, rationale, is_migration_candidate,
            pqc_ruleset_version, current },
impact    { scope: "STATICALLY_OBSERVED", node_count,
            nodes: string[], relationships: string[] },
priority  { level, score, reasons: string[] },
review    null | ApiReviewBlock,
ai_explanation_available
```

A test asserts `role` and `confidence` never appear inside `observed`.

`ApiFindingSummaryDto`

```
id, scan_id, algorithm, api, operation, role, confidence,
review_path, is_migration_candidate, priority, priority_score,
file_path, start_line, end_line, review_status
```

`ApiReviewQueueItemDto`

```
review_id, finding_id, scan_id, algorithm, api, role, review_path,
priority, priority_score, status, assigned_to, note, reasons: string[],
file_path, start_line, updated_at
```

Ordered by `priority_score` descending, then by `file_path`, `start_line`,
`id`, so equal scores never swap between requests.

`ApiExplanationDto`: `finding_id, provider, model, summary, generated_at`.

`ApiReviewBlock`: `id, status, assigned_to, note, created_at, updated_at`.

`ApiRepositoryDto`: `id, repository, language, last_inspected_at,
latest_inspection_status, findings_count`.

## Enums

The backend sends its own uppercase tokens; the frontend lowercases and
`_`-joins them (`toToken`) before matching its domain vocabulary, and tolerates
either casing.

| Field | Values sent by the backend |
|---|---|
| `inspection.status` | `QUEUED`, `RUNNING`, `COMPLETED`, `FAILED`, `CANCELLED` |
| `observed.operation` | `KEY_GENERATION`, `KEY_ESTABLISHMENT`, `SIGN`, `VERIFY`, `ENCRYPT`, `DECRYPT`, `CONSTRUCTION`, `HASH` |
| `inference.role` | `DIGITAL_SIGNATURE`, `KEY_ESTABLISHMENT`, `SYMMETRIC_ENCRYPTION`, `HASH`, `PROTOCOL`, `UNKNOWN` |
| `inference.confidence` | `HIGH`, `MEDIUM`, `LOW` |
| `migration.review_path` | `ML-DSA / SLH-DSA`, `ML-KEM`, `KEY / IMPLEMENTATION REVIEW`, `HASH / POLICY REVIEW`, `MANUAL REVIEW` |
| `priority.level` | `CRITICAL`, `HIGH`, `MEDIUM`, `LOW`, `INFORMATIONAL` (only `HIGH`/`MEDIUM`/`LOW` are produced) |
| `impact.scope` | `STATICALLY_OBSERVED` |
| `review.status` | `OPEN`, `IN_REVIEW`, `RESOLVED`, `ACCEPTED_RISK`, `FALSE_POSITIVE` |

`severity` folds priority bands onto four buckets: `CRITICAL→critical`,
`HIGH→high`, `MEDIUM→medium`, `LOW`/`INFORMATIONAL→low`.

## Review status — resolution of the known mismatch

The earlier contract listed `OPEN | IN_REVIEW | REVIEWED`. The Finding Detail
screen offers four dispositions (Keep Open, In Review, Resolved, Accept Risk,
False Positive), so the backend `ReviewStatus` enum was **widened** to
`OPEN, IN_REVIEW, RESOLVED, ACCEPTED_RISK, FALSE_POSITIVE`
(migration `c1d2e3f4a5b6`). `REVIEWED` is kept in the DB CHECK constraint as a
legacy alias for `RESOLVED`; nothing writes it, and `parse_status` maps an
incoming `REVIEWED` to `RESOLVED`. The frontend's `REVIEWED → resolved`
fallback in `mappers.ts` therefore never fires but is harmless.

`POST /findings/{id}/review` body `status` accepts
`OPEN | IN_REVIEW | RESOLVED | ACCEPTED_RISK | FALSE_POSITIVE` (case
-insensitive). Transitions are checked: an unknown token is `422`
`validation_error`; a disallowed transition is `409`
`INVALID_REVIEW_TRANSITION`. From an open state a reviewer may pick the
finding up or close it; from a closed state they may re-open it or change the
disposition; re-selecting the current state is idempotent.

A finding that is a post-quantum **migration candidate** is given an `OPEN`
review item when its scan completes, so the Review queue is populated without a
human having to touch each finding first. Other findings get a review item on
their first disposition.

## Scan lifecycle

```
POST /inspections
  → Scan(QUEUED) + ScanJob(QUEUED)          (or an existing COMPLETED scan
                                              with the same 7-part identity is
                                              returned as-is)
worker claims the job
  → Scan(RUNNING), started_at set
  → ingest_commit (GitHub archive, SSRF-guarded) → analyze_snapshot (threadpool)
  → persist_analysis: Finding + Evidence + ImpactNode rows, scan counts
  → Scan(COMPLETED), completed_at set
on failure
  → ScanJob back to QUEUED while attempts remain (max 3), then FAILED
  → Scan(FAILED) with a safe error_code / error_message
```

The worker is one in-process async loop started with the app
(`RUN_WORKER=true`). It can be disabled and run separately later. There is no
progress percentage: the frontend shows an indeterminate "analyzing" state and
polls `GET /inspections/{id}` every 2.5 s (a background refresh — no loading
flash) while the status is `QUEUED` or `RUNNING`, and stops on any terminal
state.

## Errors

Every error response is

```json
{ "error": { "code": "<stable machine code>", "message": "<safe text>" } }
```

Tracebacks, SQL, secrets and internal paths never appear. The frontend's
`http.ts` reads `error.message` / `error.code` (and still accepts a flat
`message` / `detail` / `code`). Status codes in use: `201` create, `404`
`not_found`, `409` `INVALID_REVIEW_TRANSITION`, `422` `validation_error` /
`INVALID_REPOSITORY_URL` / `INVALID_COMMIT_SHA`, `404` `COMMIT_NOT_FOUND` /
`REPOSITORY_NOT_FOUND`, `502` `INGESTION_FAILED` / `EXPLANATION_FAILED`, `503`
`EXPLANATION_UNAVAILABLE`, `500` `internal_error`.

## AI explanations

```
frontend  →  GET /findings/{id}/explanation
          →  ExplanationService  →  GeminiClient  →  Gemini
          →  Explanation row (cached per finding + prompt version)
          →  ApiExplanationDto
```

The browser never calls Gemini. `GEMINI_API_KEY` stays in the process; it is
sent only as a query parameter to the official host and never logged.
`ai_explanation_available` on a finding is `true` only when the key is set. If
generation fails the endpoint returns `502 EXPLANATION_FAILED`, the
`Explanation` row is marked `FAILED`, and the finding itself stays fully
served — the frontend panel shows an inline error with a retry.

## CORS

`CORS_ALLOW_ORIGINS` (comma-separated) controls allowed browser origins;
default `http://localhost:5173,http://127.0.0.1:5173`. Methods
`GET, POST, OPTIONS`; headers `Content-Type, Accept`; credentials off. No
wildcard by default.

## Nullability the frontend must respect

`repository.url`, `started_at`, `completed_at`, `duration_ms`,
`files_analyzed`, `end_line`, `start_column`, `end_column`,
`review` (whole block), `error_code`, `error_message`,
`latest_inspection_status`, `findings_count` (on a project) can all be `null`.

## Known follow-ups (not blocking integration)

* **Pagination.** `GET /inspections/{id}/findings` and `GET /review-queue`
  return the full set. On the acceptance commit that is ~1042 rows, which the
  frontend renders client-side. Backend cursor pagination and matching
  `?limit`/`?cursor` params are a follow-up; the frontend's `ApiListEnvelope`
  already carries `next_cursor`/`total` for when it lands.
* **`assigned_to`.** The review model has the column; no endpoint sets it yet
  (the UI shows "Unassigned").
* **Explanation fields.** `Explanation` stores `what_it_means` /
  `why_it_matters` / `review_action`; only `summary` is populated and exposed.
* **Scan timeout.** `SCAN_TIMEOUT_SECONDS` is not yet enforced by the worker.

## Out of scope (unchanged)

Docker, deployment, AWS, CI/CD, and Phases 13–16 are not implemented here.
