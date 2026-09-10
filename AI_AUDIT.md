# AI_AUDIT.md — existing AI code in Cryptiq

Audit performed 2026-09-10 before implementing the Gemini explanation layer.
Everything below was found already present in the repository; nothing was
assumed.

---

## 1. Existing AI implementation

| Area | File | State before this phase |
| --- | --- | --- |
| Model client | `cryptiq/app/integrations/gemini/client.py` | `GeminiClient` — a hand-rolled `httpx` client that POSTs to `https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent` with the API key as a `?key=` query param. Returns one **plain-text** string. Hard timeout + `maxOutputTokens` from settings. `GeminiError` for every failure. Key never logged (only the HTTP status is). **Not** the official SDK. |
| Client package | `cryptiq/app/integrations/gemini/__init__.py` | Re-exports `GeminiClient`, `GeminiError`. Docstring already states the engine never imports this package and the key never reaches the browser. |
| Explanation service | `cryptiq/app/services/explanations.py` | `explain_finding(session, finding, scan, *, client=None)`. One prompt version `explain-1`, single free-text `_PROMPT`. Caches per `(finding_id, prompt_version, status=COMPLETED)`. On `GeminiError` marks the row `FAILED`, commits, raises `ExplanationFailedError`. Bridges the async client into the sync request path with `asyncio.run`. |
| Persistence | `cryptiq/app/db/models/explanation.py` | `Explanation` model: `finding_id` FK (CASCADE, indexed), `provider`, `model`, `prompt_version`, `status` enum, plus nullable text columns `summary`, `what_was_found`, `what_it_means`, `why_it_matters`, `review_action`. `CreatedAt` + UUID PK mixins. Only `summary` / `what_was_found` are written today. |
| Enums | `cryptiq/app/db/models/enums.py` | `ExplanationStatus = {PENDING, COMPLETED, FAILED}`. `AuditEventType` already contains `EXPLANATION_REQUESTED`, `EXPLANATION_COMPLETED` (never emitted yet). |
| Backend endpoint | `cryptiq/app/api/v1/findings.py` | `GET /api/v1/findings/{finding_id}/explanation` → `ApiExplanationDto`. No POST. No audit write. |
| Wire DTO | `cryptiq/app/schemas/api.py` | `ApiExplanationDto = {finding_id, provider, model, summary, generated_at}`. `ApiFindingDto.ai_explanation_available: bool` set from `bool(settings.gemini_api_key)` in `serialize.finding_dto`. |
| Frontend control | `frontend/src/components/findings/AiExplanation.tsx` | "Explain with AI" toggle in the Finding Detail right rail. Calls `fetchFindingExplanation(finding.id)` (**GET**), shows a loading spinner, renders `explanation.summary` + a model disclaimer, has an inline error state with "Try again", and shows "AI explanation unavailable for this finding." when `finding.aiExplanationAvailable` is false. Already renders a small "Evidence used" panel from the deterministic finding. |
| Frontend service | `frontend/src/services/findings.ts` | `fetchFindingExplanation` → `GET /findings/{id}/explanation`, maps via `mapExplanation`. |
| Frontend types | `frontend/src/types/api.ts`, `types/domain.ts`, `services/mappers.ts` | `ApiExplanationDto` / `FindingExplanation` = `{findingId, provider, model, summary, generatedAt}`. |
| Frontend test | `frontend/src/components/findings/AiExplanation.test.tsx` | Covers the unavailable line and the graceful-degradation error path. |
| Backend test | `cryptiq/tests/integration/test_api_explanation.py` | Stub client asserts the finding's facts reach the prompt; covers generate-then-cache and failure-does-not-break-the-finding (expected `502 EXPLANATION_FAILED`). |

## 2. Existing dependencies

`cryptiq/pyproject.toml` had **no** Google / Gemini dependency. Runtime deps were
`fastapi, uvicorn[standard], pydantic, pydantic-settings, SQLAlchemy, alembic,
httpx`. The venv (`cryptiq/.venv`, Python 3.12, managed by `uv`) had no
`google-*` packages installed. `frontend/package.json` has no AI packages (correct
— the browser must never call Gemini).

## 3. Existing frontend AI controls

Only `AiExplanation.tsx` (+ its CSS module + test), mounted once in
`FindingDetail/FindingDetailPage.tsx` inside the right rail, after
`ReviewPathCard`. The finding detail screen already separates **OBSERVED /
INFERRED** blocks with `EpistemicBadge`s; the AI panel sits visually below them.
No other screen references AI.

## 4. Existing backend endpoints

`GET /api/v1/findings/{finding_id}/explanation` only. Routed from
`app/api/v1/router.py` via `findings.router`. No POST, no audit event, no
rate control, no explicit "not configured" branch in the route (the service
raises `ExplanationUnavailableError` 503 when `client.is_configured` is false).

## 5. Existing environment configuration

`cryptiq/app/config.py` (`pydantic-settings`, `.env` support, `extra="ignore"`)
already declares:

```
gemini_api_key: str | None = None      # env: GEMINI_API_KEY
gemini_model: str = "gemini-2.5-flash" # env: GEMINI_MODEL
gemini_timeout_seconds: int = 30
gemini_max_output_tokens: int = 1500
```

`GEMINI_API_KEY` is the existing convention and is kept. `cors_allow_origins`
already restricts the browser origins; nothing exposes settings through the API.
`test_config.py` asserts the Gemini defaults.

## 6. Security concerns found

1. **Raw REST client, plain-text output.** No structured-output contract, so the
   model's prose was stored verbatim with no schema validation — a step away from
   the "AI must not override deterministic data" rule if the summary were ever
   parsed.
2. **`asyncio.run` per request** inside a threadpool worker — fragile; replaced
   by the SDK's synchronous call.
3. **No audit trail** for explanation requests despite the enum members existing.
4. **No prompt-injection clause.** The old `_PROMPT` interpolated
   `finding.evidence.source_excerpt` directly with no instruction that source is
   untrusted data.
5. **No cache invalidation on finding change.** Cache key was
   `(finding_id, prompt_version)` with no tie to the deterministic fingerprint,
   so an explanation could outlive the finding it described.
6. **Failure code inconsistency.** Service raised `502 EXPLANATION_FAILED` /
   `503 EXPLANATION_UNAVAILABLE`; the master spec wants a single controlled
   `AI_EXPLANATION_UNAVAILABLE`.
7. **`ai_explanation_available`** is a global "is a key set" flag, not per-finding
   — acceptable (every persisted finding has evidence) but documented here.

No key was ever hard-coded, logged, returned by an endpoint, or exposed to the
frontend. That posture is preserved.

## 7. Missing functionality (implemented in this phase)

- Official `google-genai` SDK instead of the hand-rolled REST client.
- Structured JSON output validated against a Pydantic model before persist/return.
- `POST /api/v1/findings/{finding_id}/explanation` (generate-or-cache), body-free.
- Bounded input contract (one finding's evidence + deterministic conclusions —
  never repository source at large).
- Versioned prompt `gemini-explanation-v1` with explicit boundaries + an
  untrusted-source / prompt-injection clause.
- Cache identity = `finding fingerprint + prompt version + model`; stale
  explanations are never returned.
- Single controlled failure code `AI_EXPLANATION_UNAVAILABLE`; the deterministic
  finding always survives.
- Audit events `EXPLANATION_REQUESTED` / `EXPLANATION_COMPLETED`.
- Explanation persistence widened with `finding_fingerprint`, `payload` (JSON),
  `error_code`, `error_message`.
- Frontend renders the structured sections + limitations, clearly subordinate to
  the deterministic finding; switches to POST.
- Security + prompt-injection + cache regression tests; optional live test gated
  on `GEMINI_API_KEY`.
