# Cryptiq merge audit

Record of the engineering merge that made `/home/v0idsai/Projects/cryptiq` the
single canonical Cryptiq backend.

## Repository A — current build (canonical)

- Path: `/home/v0idsai/Projects/cryptiq`
- Git: initialised during this merge; baseline commit `2c3a93a`, tag
  `pre-merge-baseline`
- State before merge: 380 tests passing, ruff clean, Alembic head
  `42c2c7f7e9dc`
- Layout: `app/` package, FastAPI + SQLAlchemy 2.x + Alembic + pydantic-settings

## Repository B — second build

- Path: `/home/v0idsai/Projects/cryptiq-1`
- Git: `86687f9958f50877be4ccb215384a60e218bf967` on `main`, tag
  `pre-merge-backup`
- Commits: `cd0b6cc` (init), `57695fa` (Phases 9–12), `86687f9` (merge PR #1)
- State before merge: 33 tests passing under `unittest` (no pytest, no ruff
  configuration); 160 ruff findings when linted with this project's settings
- Layout: `src/cryptiq/` package, standard library only, `requires-python >= 3.9`

### What Repository B actually contained

The claim was "approximately Phase 5 through Phase 12". That is not what the
code shows. Its own `README.md` states "Phases 9–12", and the source agrees:

| Present | Absent |
|---|---|
| `impact/` (analyzer, graph, models) | Any HTTP API, config, or settings |
| `priority/` (scorer, rules) | Alembic, SQLAlchemy, PostgreSQL-compatible schema |
| `cache/` (fingerprint, scan identity) | GitHub ingestion, SSRF controls, archive safety |
| `worker/` (service, worker loop, job state machine) | File discovery |
| `storage/` (raw `sqlite3` DDL and repositories) | Python AST parser |
| `core/` (dataclass domain models, enums) | Any cryptographic rule, including RSA |
| `compat/interfaces.py` (protocols for the phases it did not have) | Evidence engine, role engine, PQC mapper |

There is therefore **no Phase 5, 6, 7 or 8 in Repository B**, and no overlap at
all with Phases 1–5. The two builds are complementary, not competing, except in
the domain model and persistence layer, where they conflict directly.

Repository B's only integration test uses a hardcoded fake source provider
pointing at `/tmp/pyca-cryptography` and an analysis engine returning canned
matches. It performs no real-repository verification.

## Phase comparison

| Phase | Repository A | Repository B | Selected | Why |
|---|---|---|---|---|
| 1 — Backend foundation | FastAPI app, settings, error contract, health endpoints | absent | **A** | Only implementation. |
| 2 — Database | SQLAlchemy 2.x, 9 entities, Alembic, PostgreSQL-compatible | raw `sqlite3` DDL, dataclass models | **A** | A is migration-managed and portable to PostgreSQL, which is a stated requirement. B's schema is SQLite-only DDL executed at startup, with no migration history. |
| 3 — GitHub ingestion | exact-commit retrieval, SSRF host allowlist, DNS checks, manual redirect validation, archive limits, traversal and symlink defence | absent | **A** | Only implementation, and the security boundary the merge must not weaken. |
| 4 — Python AST parser | full parser, contexts, import index, batch parsing | absent | **A** | Only implementation. |
| 5 — RSA detection | `PY-CRYPTO-RSA`, five APIs, five evidence bases, verified on the real acceptance commit | absent | **A** | Only implementation, and already verified against `pyca/cryptography` at the acceptance commit. |
| 6 — Evidence engine | absent | `Evidence` dataclass carrying `code_snippet`, populated by the worker | **Merged** | B's concept (a snippet attached to a finding), rebuilt as `app/engine/evidence/` against A's `RuleMatch` and AST spans, and written to respect A's snapshot-lifetime rule. |
| 7 — Additional crypto rules | absent | absent | — | Neither build has ECDSA, Ed25519, ECDH, X25519, AES or hash rules. |
| 8 — Role engine | absent | `CryptoRole` enum only, values expected from a phase that does not exist | — | No role classifier in either build. The enum alone establishes nothing, so no role is asserted. |
| 9 — Impact analysis | `ImpactNode` table only | `ImpactAnalyzer` + `ImpactGraph`, evidence-hierarchy chain | **Merged (B's design, rebuilt)** | B's algorithm → API → function → class → file chain is sound and maps onto A's `ImpactNode` columns. Rebuilt against A's models and enums, with two corrections (below). |
| 10 — Priority | `ReviewPriority` enum only | `PriorityScorer` + algorithm tables | **Merged (B's design, rebuilt)** | B's fixed-table scoring with recorded reasons is the only implementation and is genuinely deterministic. Rebuilt against A's `RuleMatch` and A's five-value priority vocabulary. |
| 11 — Fingerprints / scan cache | `fingerprint(*parts)` primitive, `Scan` version stamps | `FingerprintEngine`, `ScanIdentity`, `ScanCacheManager` | **Merged (best of both)** | B's labelled canonical string and seven-part scan identity are adopted. B's finding fingerprint inputs are rejected (below). Cache lookup rewritten as a SQLAlchemy query against A's `Scan`/`Repository`. |
| 12 — Scan worker | `ScanJob` model shaped for a claimable queue | `ScanWorker` loop, `JobStateMachine`, `ScanService` | **Partially merged** | B's job state machine and retry bounds adopted. B's worker loop and `ScanService` discarded (below). |

### Tests proving each selection

| Selection | Evidence |
|---|---|
| Phases 1–5 kept | 380 pre-merge tests still pass unchanged after the merge. |
| Evidence engine | `tests/integration/test_pipeline.py` asserts the excerpt equals the exact AST span; `test_acceptance_real.py` asserts the called method appears in every real excerpt. |
| Impact | `tests/unit/test_impact.py` (11 tests) covers the full chain, missing class, module-level call, deduplication and identifier determinism. |
| Priority | `tests/unit/test_priority.py` (23 tests) pins every algorithm-table branch, both thresholds and the post-quantum short circuit. |
| Fingerprints | `tests/unit/test_fingerprints.py` (21 tests) plus two pipeline tests proving a fingerprint survives a line insertion and changes when the call moves to another function. |
| Scan cache | `tests/integration/test_scan_cache.py` (8 tests) proves every one of the seven identity parts must match and that only COMPLETED scans qualify. |
| Job lifecycle | `tests/unit/test_scan_jobs.py` (16 tests) covers every legal and illegal transition and the retry ceiling. |
| Whole pipeline | `tests/integration/test_pipeline.py` (10 tests) and `tests/integration/test_acceptance_real.py` (10 opt-in tests against the real commit). |

## What was discarded from Repository B, and why

| Discarded | Reason |
|---|---|
| `storage/db.py`, `storage/repositories.py`, `storage/transaction.py` | A competing persistence stack: raw `sqlite3` with DDL executed at startup, no migrations, SQLite-only (`CREATE UNIQUE INDEX ... WHERE`, `PRAGMA journal_mode=WAL`). Repository A's SQLAlchemy + Alembic schema is migration-managed and PostgreSQL-compatible, which the project requires. Keeping both would mean two sources of truth for the same tables. |
| `core/models.py` (`Finding`, `Scan`, `ScanJob`, `Evidence`, `ImpactNode`) | Duplicate representations of domain concepts that Repository A already has as SQLAlchemy models with a migration history. One canonical model per concept; B's side was adapted to A's. |
| `core/enums.py` | Same vocabularies under different names and values (`ConfidenceLevel` CONFIRMED/INFERRED/UNKNOWN against A's HIGH/MEDIUM/LOW; `RetrievalMode` against A's `SourceState`; `PriorityLevel` three values against A's five). A's are already persisted and migrated. |
| `worker/worker.py`, `worker/service.py` | Two blocking problems. First, `ScanService` depends on the discarded `sqlite3` repositories and on a Phase 6–8 pipeline that exists in neither build. Second, its `SourceProvider` protocol is synchronous and returns a snapshot whose path outlives the call, which contradicts Repository A's rule that the snapshot exists only inside `async with ingest_commit(...)`. Porting it would have introduced exactly the source-lifetime bug the merge had to avoid. `worker/job.py`'s state machine was kept. |
| `compat/interfaces.py` | Protocols describing phases Repository B did not have. Repository A's `SourceProvider` protocol and `RuleMatch` are the real ones. |
| B's finding fingerprint inputs (`commit_sha`, `start_line`) | Both defeat the purpose of a fingerprint. Including `commit_sha` means every finding is new in every scan and nothing is ever UNCHANGED or RESOLVED. Including `start_line` means inserting a line above a call renames the finding. The labelled canonical-string construction was kept; those two inputs were not. |
| B's `str`-mixin enums, `Optional[X]`/`Dict[...]` typing, `_extract_val` duck-typing helpers | Repository A targets Python 3.12+ and uses `StrEnum` and modern unions. The defensive `getattr`-or-`dict` accessors existed to bridge to models that did not exist; against real typed models they only hide errors. |
| B's `unittest` suite (33 tests) | Rewritten as pytest tests against the merged models. The behaviours they covered are covered by the 90 new tests listed above; the originals asserted against discarded models. |

## Defects found in Repository B while auditing

1. `worker/service.py` uses `JobStatus` in `request_scan` without importing it.
   Reproduced: `request_scan(..., job_repo=JobRepository(conn))` raises
   `NameError: name 'JobStatus' is not defined`. Not covered by its tests.
2. `ImpactAnalyzer` derives every node identifier from a `uuid4` finding id, so
   the same finding produces a different graph on every run. The rebuilt
   analyzer derives identifiers from the node's own type and label.
3. `ImpactNodeType.MODULE` is defined but never used; no module node is ever
   produced. The rebuilt analyzer emits one from `ParsedFile.module_path`.
4. `storage/repositories.py` annotates a local as `list[Any]` without importing
   `Any`. Harmless today only because local annotations are not evaluated.

## Important compatibility decisions

### Schema

- One canonical set of models: `app/db/models/`. Repository B's dataclasses were
  not carried over.
- `ScanJob` gained two columns the worker needs: `max_attempts` (default 3) and
  `locked_by`. Both come from Repository B's `scan_jobs` DDL.
- No `impact_edges` table was added. Repository B stored edges separately;
  Repository A's `ImpactNode` carries its `relationship` inline, which is enough
  for the chain the analyzer produces and avoids a table with no reader.

### Migrations

- One linear history, extended rather than replaced:
  `dec2cc3d8453` (baseline) → `42c2c7f7e9dc` (domain schema) →
  `d1449ca9aa37` (scan job retry bounds and lock owner).
- No migration file from Repository B was copied; it had none.
- `max_attempts` is added `NOT NULL` with `server_default=3` so the migration
  applies to a table that already holds rows.
- Verified: fresh upgrade to head, downgrade to `42c2c7f7e9dc`, upgrade again.

### Engine and database boundary

- The engine never imports `app.db`. Vocabularies the engine needs
  (`ImpactNodeType`, `ImpactRelationship`, `ReviewPriority`) are restated in the
  engine by value and mapped at the persistence boundary. A test asserts the
  engine's `ReviewPriority` values equal the persisted ones.
- The engine's `MatchConfidence` has a fourth value, `UNKNOWN`, which no rule
  emits. The persistence layer must map explicitly rather than pass it through.

### Parser and rule interfaces

- `RuleMatch` (Repository A) is the single raw-observation type. Repository B's
  `compat.RuleMatch` was not adopted.
- Rules see only `Call` nodes, once each, so one construct yields one
  observation.

### Fingerprints

- Finding identity is `repository, file_path, rule_id, algorithm, api,
  operation, enclosing_function, enclosing_class`, each written with its own
  label so a value moving between fields cannot collide.
- Deliberately excluded: commit SHA, line numbers, columns, timestamps, random
  values.
- Consequence, tested and documented: two identical calls in the same function
  share a fingerprint. On the acceptance commit, 38 findings carry 34 distinct
  fingerprints. This is the intended trade-off — it is what lets a finding
  survive an edit — but it means the persistence layer must deduplicate under
  `UNIQUE(scan_id, fingerprint)` rather than insert each call site.
- Scan identity is Repository B's seven-part tuple, adopted unchanged in shape:
  provider, owner, name, commit SHA, parser version, ruleset version, PQC
  ruleset version.

### Versioning

- `parser_version`, `ruleset_version` and `pqc_ruleset_version` continue to come
  from `Settings` through `engine_versions()`. `pqc_ruleset_version` is stamped
  and carried but nothing reads it yet, because no PQC mapper exists.

### API

- No endpoints were added. Repository B had none, and a scan endpoint would need
  the worker that was deliberately not merged. `/health` and `/api/v1/health`
  are unchanged.

### Dependencies

- No dependency was added. Repository B declared none and used only the standard
  library. `pyproject.toml` is unchanged by this merge.
