# CACHE_BEHAVIOR.md — scan cache and explanation cache

Two independent caches. Both key on deterministic identity, never on wall-clock
or a request counter.

---

## 1. Scan cache

### Identity

A scan is a pure function of its **7-part `ScanIdentity`**
(`app/engine/fingerprints/__init__.py`):

```
provider, owner, name, commit_sha, parser_version, ruleset_version, pqc_ruleset_version
```

`POST /api/v1/scans` normalises the repository URL and commit SHA, upserts the
`Repository`, and looks for an existing **COMPLETED** `Scan` with the same
identity (`app/services/scans.py::create_scan`).

### Behaviour

| Request | Response | Work done |
| --- | --- | --- |
| First submit of a commit | `202 Accepted`, `status: QUEUED`, `cached: false` | `Scan(QUEUED)` + `ScanJob(QUEUED)` created; the worker runs the engine |
| Re-submit of the **same** repo + commit after it completed | `200 OK`, `status: COMPLETED`, `cached: true` | none — the stored `Scan` is serialised as-is |
| Same repo, **different** commit | `202`, new scan | full analysis |
| Same commit after a `ruleset_version` / `parser_version` / `pqc_ruleset_version` bump | `202`, new scan | full analysis (the identity changed) |
| A `FAILED` scan of a commit, then re-submit | `202`, new scan | full analysis (only COMPLETED scans are served from cache) |

### Verified (this pass, live)

Acceptance commit `pyca/cryptography @ 1f903f5ed2e5e316f345a927555e48535829d8de`,
already persisted in `cryptiq/cryptiq.db` (1 scan, 1042 findings, 132 review
items):

- **API:** `POST /api/v1/scans` with that repo+commit →
  `HTTP/1.1 200 OK`, body `... "findings_count":1042 ... "cached":true`.
- **Browser:** the Inspect form submitted the same repo+commit → landed on the
  completed report immediately, "1,042 findings", no queued/running phase, no
  worker run.
- **CLI:** `python -m app.cli scan <repo> <commit>` → `Status: CACHED`,
  `Existing result reused.`
- No duplicate `Scan`, `Finding`, `Evidence`, `ImpactNode` or `ReviewItem` rows
  were created by the re-submits. Fingerprints are stable 64-char hex digests.
  Row counts before and after the re-submits were identical.

The single stored scan and its one COMPLETED `ScanJob` are the only rows for
that identity; a stale orphan `ScanJob` (RUNNING, referencing a deleted scan)
found during the audit was removed so the demo DB has no impossible state.

### `test_scan_cache.py`

`tests/integration/test_scan_cache.py` (8 tests) pins that **every** one of the
seven identity parts must match for a hit, and that only `COMPLETED` scans
qualify.

---

## 2. Explanation cache

### Identity

`app/services/explanations.py::_cached_explanation`:

```
finding_id  +  finding.fingerprint  +  prompt_version  +  model  +  status == COMPLETED
```

`prompt_version` is `gemini-explanation-v1` (`app/services/gemini.py`); bump it
whenever the system instruction or the input/output contract changes and every
stored explanation is transparently invalidated.

### Behaviour

| Request | Response | Model call |
| --- | --- | --- |
| First `POST /findings/{id}/explanation` for a finding (key set) | `200`, `cached: false`, structured sections | yes — then persisted `COMPLETED` |
| Second request, finding unchanged | `200`, `cached: true` | **no** — the stored row is returned |
| Request after the finding's deterministic fingerprint changed | `200`, `cached: false` | yes — the old row no longer matches; a stale explanation is never served |
| `prompt_version` or `model` changed | `200`, `cached: false` | yes |
| Any AI failure (not configured, timeout, quota, auth, malformed output) | `503 AI_EXPLANATION_UNAVAILABLE` | attempt persisted as `status=FAILED`; the finding is untouched |

Explanations are **on demand only**. Scanning never calls Gemini: a
1000-finding scan makes zero model calls and writes zero `Explanation` rows.

### Verified (this pass)

- No `GEMINI_API_KEY` in the environment, so `POST /findings/{id}/explanation`
  returned `503 {"error":{"code":"AI_EXPLANATION_UNAVAILABLE","message":"AI
  explanations are not configured."}}` and the finding detail rendered fully with
  "AI explanation unavailable for this finding." A prior `FAILED` `Explanation`
  row for that finding is retained by design.
- Cache-hit / stale-invalidation / no-call-on-cache are covered by
  `tests/integration/test_api_explanation.py` and `tests/unit/test_gemini_service.py`
  with a faked SDK (in the 759 passing backend tests).

---

## 3. Frontend does not double-fetch

- `useAsyncResource` aborts a superseded request; `net::ERR_ABORTED` entries in
  the console are cancelled polls, not errors.
- Polling of `GET /scans/{id}` and the findings page stops the instant the scan
  reaches a terminal state.
- The findings table is always paginated (50/page — 521 pages on the acceptance
  commit); it never fetches all rows.
- "Explain with AI" is a manual action; the explanation is fetched once and the
  panel does not re-request on re-render.
