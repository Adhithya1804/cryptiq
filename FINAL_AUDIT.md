# FINAL_AUDIT.md — Cryptiq coherence audit

Date: 2026-09-10
Workspace: `/Users/aadhi/cryptiq-2` (not a git repo). Two projects:
`cryptiq/` (FastAPI backend + engine + CLI, its own git repo) and `frontend/`
(React 18 + Vite 5 + TS strict, its own git repo).

This audit is a coherence pass, not a feature phase. Nothing in the analysis
architecture was changed. The full story holds end to end:

```
GitHub repo → exact commit → SSRF-guarded ingestion → Python AST → deterministic
rule → exact source evidence → inferred role → PQC review path → bounded impact →
deterministic priority → review queue → optional AI explanation → cache
```

AI is strictly downstream of deterministic analysis and cannot change a detected
value.

---

## 1. Architecture

| Layer | Location | Role |
| --- | --- | --- |
| Ingestion | `cryptiq/app/engine/ingestion/`, `app/integrations/github/` | Fetch one exact commit from GitHub as a verified snapshot, under SSRF, size and file-count limits. Snapshot lives only inside `async with ingest_commit(...)`. |
| Parser | `app/engine/parser/` | Python AST only. `parser_version = python-ast-1`. |
| Rules | `app/engine/rules/` | RSA, ECDSA, Ed25519, ECDH, X25519, AES, hashes — all against the Python `cryptography` library. Syntax only, never text. `ruleset_version = 0.3.0`. Output: `RuleMatch`. |
| Evidence | `app/engine/evidence/` | Exact source excerpt for the AST span, plus `rule_id` / version stamps. |
| Roles | `app/engine/roles/classifier.py` | Fixed table `(algorithm, operation) → CryptographicRole` + a fixed rationale sentence. No model, no scoring. |
| PQC | `app/engine/pqc/mapper.py` | Fixed table `(algorithm family, role) → PqcReviewPath` + rationale + `is_migration_candidate`. `pqc_ruleset_version = 0.2.0`. |
| Impact | `app/engine/impact/analyzer.py` | Bounded static chain algorithm → API → function → class → module → file. Node identity derived from node type + label (deterministic). |
| Priority | `app/engine/priority/` | Fixed algorithm/operation tables → `level`, integer `score`, list of reason strings. Post-quantum short-circuit. |
| Fingerprints | `app/engine/fingerprints/` | `finding_fingerprint` over `repository, file_path, rule_id, algorithm, api, operation, function, class` (labelled parts). `ScanIdentity` = 7-part tuple. Line numbers, columns, commit SHA deliberately excluded. |
| Persistence | `app/services/persistence.py` | Reshapes `AnalysisResult` into rows. Never recomputes a role/priority/fingerprint, never re-reads source. Dedups by fingerprint per scan. Auto-opens an `OPEN` `ReviewItem` per migration candidate. |
| Worker | `app/worker.py` | One in-process async loop (`RUN_WORKER=true`). Claim job → RUNNING → ingest + analyse (engine in a threadpool) → persist → COMPLETED. On error: retry to `max_attempts` (3) then FAILED with a safe `error_code`. |
| API | `app/api/v1/` | `/scans`, `/findings`, `/review-queue`, `/review-items`, `/projects`, plus the legacy `/inspections` surface. |
| Serialize | `app/services/serialize.py` | Rows → wire DTOs. Only computed value: PQC review path, replayed as a pure lookup on the stored algorithm + role. |
| Explanations | `app/services/explanations.py`, `app/services/gemini.py`, `app/integrations/gemini/client.py` | Gemini restates one already-established finding. Config gate → cache lookup → audit → call → schema-validate → persist. Single failure code. |
| Frontend | `frontend/src/` | One HTTP boundary (`services/http.ts`), one canonical endpoint client (`services/client.ts`), wire→domain mappers, `useAsyncResource`. Never computes an analysis value. |
| CLI | `cryptiq/app/cli/` | Thin `httpx` client of the running API. Never imports the engine or DB. |

## 2. Backend

FastAPI + SQLAlchemy 2.0 + Alembic + pydantic-settings. SQLite by default,
PostgreSQL-compatible schema. Alembic head `f4a5b6c7d8e9`. Error contract:
every failure is `{ "error": { "code", "message" } }` with a stable machine code
and safe text — no tracebacks, SQL, secrets or internal paths. Config via
`.env` (git-ignored) / environment; `.env.example` carries names only, no
secrets.

## 3. Analysis engine

Deterministic and reproducible: the same commit + the same 7-part scan identity
always yields the same findings. Confirmed by re-submitting the acceptance
commit (`cached: true`, no re-analysis) and by 759 backend tests including
golden-file rule tests and an opt-in real-repository acceptance test.

## 4. Persistence

9 domain models. One `Finding` row per `(scan, fingerprint)`; duplicate engine
matches (same construct twice in a function) fold into the first in deterministic
order. `ImpactNode` carries its `relationship_type` inline (nullable for the
root node). `priority_score` / `priority_reasons` / `role_rationale` are columns
so the API exposes engine output without recomputing it.

## 5. Worker

Lifecycle `QUEUED → RUNNING → COMPLETED | FAILED`. Retry to 3 attempts then
FAILED. Verified live: a well-formed but non-existent commit went
`QUEUED → RUNNING → FAILED` with `error_code = COMMIT_NOT_FOUND`, no dangling
job, no stack trace, worker still serving. `ingest_commit`'s `finally` block
`rmtree`s the snapshot; the archive download is a `NamedTemporaryFile` context
manager. (A hard-killed process can still orphan a temp file — see Limitations.)

## 6. API

Acceptance-tested live (all correct status + schema):

| Endpoint | Result |
| --- | --- |
| `POST /api/v1/scans` | `202` queued / `200` `cached:true` |
| `GET /api/v1/scans/{id}` | `200` `ApiInspectionDto` (+ `error_code`/`error_message`) |
| `GET /api/v1/scans/{id}/findings?page=&page_size=&priority=&algorithm=&role=&status=&confidence=` | `200` `{items,total,page,page_size,pages}`; `page_size` capped 200; unknown enum → `422` |
| `GET /api/v1/findings/{id}` | `200` grouped `observed / inference / migration / impact / priority / review` |
| `GET /api/v1/review-queue` | `200` `{items,total}`, ordered by `priority_score` desc then `file_path,start_line,id` |
| `PATCH /api/v1/review-items/{id}` | `200`; omitted fields untouched, `null` clears |
| `POST /api/v1/findings/{id}/explanation` | `200` structured explanation, or `503 AI_EXPLANATION_UNAVAILABLE` |

## 7. Frontend

React 18 strict. One-directional data flow UI → page → `useAsyncResource` →
service → HTTP. Every data screen renders exactly one of loading / error / empty
/ success. "No backend connected" mode when `VITE_API_BASE_URL` is unset —
nothing is fabricated. Findings list paginates 50/page; the algorithm filter is
server-side and resets to page 1. Polls `GET /scans/{id}` every 2 s while
queued/running and stops on any terminal state. Coherence-pass changes:

- Failed-scan report now shows an "Analysis failed" notice with the API's
  `error_message` + `error_code` (was: silent empty state).
- Review-queue reason text no longer renders a doubled period between/after
  sentences.

## 8. CLI

`cryptiq` console script (`app.cli.main:main`) or `python -m app.cli`. Commands:
`scan`, `scan-status`, `findings`, `finding`, `review-queue`, `review-update`,
`demo`. Every command takes `--json` (raw API schema). Exit codes 0/1/2/3/4. No
expected error prints a traceback. Verified live against the running API:
`scan` → `CACHED`, `finding` → full grouped detail with `N/A` for nulls.

## 9. Gemini

`google-genai` SDK, pinned `>=1.0,<3.0`. Single seam: `app/services/gemini.py`
(only importer of `GeminiClient`). Endpoint `POST /findings/{id}/explanation`
takes **no request body** — the finding id is the whole input, so a browser
cannot inject prompt or source text. Bounded input: one finding's deterministic
facts + a ≤2 000-char excerpt + ≤40 impact labels. Output validated against
`GeminiExplanationPayload` (six explanatory strings + `limitations`) before
persist or return. System instruction forbids re-classification and treats the
excerpt as untrusted data. Cache identity = `finding fingerprint + prompt
version + model`; a changed finding never returns a stale explanation. Single
failure code `AI_EXPLANATION_UNAVAILABLE` (503); failed attempts persist as
`status=FAILED`. Audit events `EXPLANATION_REQUESTED` / `EXPLANATION_COMPLETED`.
Deterministic fields are read from their own rows at render time, never from the
explanation. Details: `AI_EXPLANATION.md`.

## 10. Tests

| Suite | Result |
| --- | --- |
| Backend `pytest` | **759 passed, 34 skipped** (skips: opt-in network + `gemini_live` without a key) |
| Backend `ruff check .` | clean |
| Backend CLI tests (`tests/unit/test_cli.py`, in the 759) | 25 passed |
| Frontend `vitest run` | **57 passed** |
| Frontend `tsc -b --noEmit` | clean |
| Frontend `eslint --max-warnings 0` | clean |
| Frontend `vite build` | ok |

## 11. Known limitations

- **Supported language:** Python only. **Supported library:** the Python
  `cryptography` package only.
- **Rules:** RSA, ECDSA, Ed25519, ECDH, X25519, AES, hashes. No DSA, no DH, no
  TLS/protocol recognition, no other libraries (`pyca`'s own `_rust` bindings are
  deliberately out of scope).
- **Role table** leaves RSA key-generation `UNKNOWN` on purpose (dual-use).
  `PROTOCOL` is in the vocabulary but nothing emits it.
- **PQC mapping is a review path, not a drop-in replacement.** Uncovered
  `(algorithm, role)` combinations fall through to `MANUAL REVIEW`.
- **Impact** is a bounded static chain within the scanned snapshot; no
  cross-repo or runtime call graph. `relationships` has one fewer entry than
  `nodes` (the root node has no inbound relationship).
- **Priority** is a migration-review triage signal, not a vulnerability
  severity. `score`/`reasons` can be null/empty for a bare finding; the UI and
  CLI show that state rather than inventing one. The Finding Detail screen shows
  the priority level but not the reason list (reasons appear in the Review
  queue).
- **AI dependency:** requires `GEMINI_API_KEY`. Without it the explanation
  endpoint returns `503 AI_EXPLANATION_UNAVAILABLE` and every finding is fully
  usable. The live round-trip was not exercised in this pass (no key available);
  the generate/validate/cache/persist/audit path and the prompt-injection
  boundary are covered by `tests/integration/test_api_explanation.py` (16) and
  `tests/unit/test_gemini_service.py` (10) with a faked SDK, and
  `tests/integration/test_gemini_live.py` runs one real round trip when a key is
  set.
- **`SCAN_TIMEOUT_SECONDS`** is configured but not enforced by the worker.
- **`assigned_to`** is settable only through `PATCH /review-items/{id}`; there
  is no dedicated UI control.
- **Review transition table** currently permits every pair among the five
  statuses, so `409 INVALID_REVIEW_TRANSITION` is latent (the frontend still
  handles it).
- **Temp cleanup:** the current code removes the snapshot dir and the archive
  file on every exit path, but a `SIGKILL` mid-download can still orphan a
  `cryptiq-archive-*.zip` in the system temp dir.
- **Deployment:** local/demo only. No Docker, AWS, Kubernetes, CI/CD, or
  authentication — all deliberately out of scope.
- **Git state:** `cryptiq/`'s API/persistence/worker/CLI/Gemini layer and the
  entire `frontend/` tree are uncommitted working-tree files (see STEP 24 in the
  final report). No secrets, databases, or build artifacts are tracked or
  staged; `.gitignore` covers `.env`, `*.db`, `dist/`, caches, and now
  `.DS_Store`.
