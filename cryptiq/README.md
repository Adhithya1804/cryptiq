# Cryptiq

Deterministic cryptographic static-analysis backend.

Cryptiq analyses a repository at an exact commit and produces reproducible
findings about its use of cryptography. The engine is deterministic: the same
commit and the same rule set always yield the same findings.

## Local setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

cp .env.example .env

alembic upgrade head
RUN_WORKER=true uvicorn app.main:app --port 8000
```

`RUN_WORKER=true` (the default) runs the scan worker in-process with the API,
so queued scans execute without a separate process.

Then:

```bash
curl http://localhost:8000/health
curl http://localhost:8000/api/v1/health
```

## CLI

`cryptiq` is the standalone CLI to the analysis engine. It runs in two modes
over the **same** engine — see [`CLI.md`](CLI.md) for the full reference.

**Local** (offline; runs the engine in-process, no API/DB/Docker needed):

```bash
cryptiq scan .                                   # working tree
cryptiq scan /path/to/repo --commit <sha>        # exact commit via `git archive`
cryptiq scan . --format sarif                    # valid SARIF 2.1.0
cryptiq diff --base <sha> --head <sha>           # fingerprint diff: NEW/FIXED/UNCHANGED
cryptiq version
```

**Remote** (thin HTTP client of a running Cryptiq API):

```bash
cryptiq scan https://github.com/org/repo --remote --commit <sha>
cryptiq scan https://github.com/org/repo --remote --commit <sha> --wait --format sarif
cryptiq scan-status <scan_id>
cryptiq findings <scan_id> --algorithm rsa --priority high
cryptiq finding <finding_id> --grouped
cryptiq review-queue --status open --json
cryptiq review-update <review_id> --status in_review --assignee alice
cryptiq demo        # submit + poll + summarise the acceptance scan
```

Install with `pip install -e ".[dev]"` (console script `cryptiq`) or run
`python -m app.cli`. Remote API URL: `--api-url`, then `$CRYPTIQ_API_URL`, then
`http://localhost:8000/api/v1`. Every command takes `--json`. Exit codes:
`0` ok / no blocking findings, `1` findings need attention (or generic remote
failure), `2` bad arguments, `3` operational error, `4` remote resource not
found. See [`CLI.md`](CLI.md), `../DEMO_RUNBOOK.md` and `../CLI_AUDIT.md`.

## Frontend

The React frontend lives in `../frontend` (`npm run dev`, port 5173) and
consumes the `/api/v1/scans`, `/api/v1/findings` and `/api/v1/review-queue`
endpoints.

## Tests

```bash
pytest                                    # unit, integration and security tests
CRYPTIQ_RUN_NETWORK_TESTS=1 pytest -m network   # opt-in, reaches github.com
ruff check .
```

## Pipeline

```
Repository -> exact commit -> source snapshot -> file discovery
  -> Python AST parser -> cryptographic rules -> source evidence
  -> bounded impact -> migration review priority -> fingerprint
```

`app/engine/pipeline.py` runs the whole chain over one extracted snapshot.
The snapshot exists only inside `async with ingest_commit(...)`, so every
stage that reads source runs within that block.

## Supported analysis scope

Cryptiq provides deterministic cryptographic migration analysis for **supported
APIs in the Python `cryptography` library**. The analysis engine — AST parsing,
role inference, PQC review-path mapping, impact and priority — is
library-agnostic; coverage is defined entirely by the rule set, which is
extensible to further cryptographic libraries by adding rules under
`app/engine/rules/`.

| | |
|---|---|
| **Language** | Python (`ast`-based; no target code is executed) |
| **Library** | `cryptography` (pyca) |
| **Rules** | RSA, ECDSA, Ed25519, ECDH, X25519, AES, hashes |
| **Not yet covered** | PyCryptodome (`Crypto.*`), PyNaCl (`nacl.*`), stdlib `hashlib`, DSA, DH, TLS/protocol recognition — tracked as future rule-set scope, not a defect |

A repository outside this scope (or one with no cryptography at all) scans
cleanly and returns zero findings rather than guesses — the engine is precise
about what it can establish from syntax and silent about the rest. Coverage of
additional libraries is additive: a new rule does not change any existing
finding or its fingerprint.

A finding separates what was observed from what was inferred: the algorithm,
API, location and source excerpt can be checked against the file, while the
cryptographic role, the post-quantum review path, the impact and the priority
follow from them. `FRONTEND_BACKEND_CONTRACT.md` records the response shape.

Persistence, the scan API (`POST /scans` → `202` queued / `200` cached), the
in-process worker, review items and the review queue are all implemented and
exercised by the CLI and frontend.

## Context-Aware Migration Advisor

> *"CRYPTIQ does not equate cryptographic algorithm detection with migration advice."*

The Context-Aware Migration Advisor evolves CRYPTIQ from pattern matching ("detect crypto → map to PQC") into semantic, context-aware architectural reasoning ("detect crypto → understand semantic role → understand application constraints → consult authoritative standards → produce context-aware migration assessment").

### Three-Tier Epistemic Architecture

CRYPTIQ enforces a strict epistemic hierarchy across three distinct tiers:

1. **FACT (Deterministic Observation)**:
   - Established strictly by the static analysis AST engine.
   - Immutable: algorithm (`SHA-256`, `ECDSA`, `ECDH`), location, API, lines, source excerpt, fingerprint.
   - Downstream models and advisors cannot modify, dispute, dismiss, or invent findings.

2. **CONTEXT (Application Domain & Engineering Constraints)**:
   - Application domain profiles (`AUTONOMOUS_DRONE`, `CLOUD_INFRASTRUCTURE`, `FINTECH`, `HEALTHCARE`, `GENERAL_SOFTWARE`).
   - Physical and operational constraints: bandwidth limits, latency sensitivity, compute/memory restrictions, battery/power limits, payload size sensitivity, offline air-gapped operation.

3. **RECOMMENDATION (Authoritative Guidance & Trade-offs)**:
   - Advisory decisions: `KEEP`, `REVIEW`, `MIGRATE`, `INSUFFICIENT_CONTEXT`.
   - Post-quantum migration candidates: `ML-KEM-768` (NIST FIPS 203), `ML-DSA-65` (NIST FIPS 204), `SLH-DSA` (NIST FIPS 205).
   - In-process RAG knowledge retrieval: BM25 matching against authoritative NIST standards (FIPS 203/204/205, SP 800-131A, SP 800-107) and avionics literature.
   - Concrete engineering trade-offs (e.g., lattice signature expansion from 64B to ~3.3 KB and telemetry bandwidth impact).
   - Semantic guardrails: Hard deterministic invariants preventing category errors (e.g. attempting to map hash deduplication to ML-DSA or digital signatures to ML-KEM).

### Concrete Scenario Comparison

| Scenario | Detected Cryptography | Contextual Role | Domain Context | Advisor Decision | Migration Candidate | Engineering Trade-offs & Rationale |
|---|---|---|---|---|---|---|
| **Map Tile Deduplication** (`tile_cache.py:142`) | SHA-256 (`hashes.SHA256`) | `CONTENT_ADDRESSING` | Autonomous Drone (embedded Linux, low bandwidth) | **KEEP** | *None* | Zero signature size overhead. SHA-256 remains collision-resistant under Grover's algorithm (128-bit security). Mapping to ML-DSA is a category error. |
| **Firmware Update Verification** (`verifier.py:28`) | ECDSA (`ec.ECDSA`) | `FIRMWARE_SIGNING` | Autonomous Drone (lossy telemetry radio) | **MIGRATE** | `ML-DSA-65` (FIPS 204) | ECDSA is quantum-vulnerable. Migration to ML-DSA-65 incurs signature expansion (64B → ~3.3 KB), affecting telemetry payload limits. |
| **Ground Link Key Agreement** (`channel.py:15`) | ECDH (`ec.ECDH`) | `KEY_ESTABLISHMENT` | Cloud Infrastructure | **MIGRATE** | `ML-KEM-768` (FIPS 203) | Vulnerable to Shor's algorithm. Must migrate to a post-quantum Key Encapsulation Mechanism (ML-KEM), *never* a digital signature scheme. |

### CLI Usage

```bash
# Scan local repository with domain profile context
cryptiq scan . --domain autonomous-drone
cryptiq scan . --domain cloud-infrastructure --format json
cryptiq scan . --domain fintech --format sarif

# Inspect single finding with contextual advice
cryptiq finding <finding_id> --domain autonomous-drone
```

### API Endpoints

- `POST /api/v1/findings/{finding_id}/migration-assessment`: Generate (or return cached) contextual migration assessment. Accepts optional `domain_profile` in request body.
- `GET /api/v1/findings/{finding_id}/migration-assessment?domain=AUTONOMOUS_DRONE`: Retrieve assessment for a finding under a specified domain.

AI explanation: `POST /findings/{id}/explanation` (with a `GET` alias) generates
a bounded, structured natural-language explanation of an **already-established**
finding through Gemini, cached per `finding fingerprint + prompt version +
model`. It never discovers, re-classifies or overrides a deterministic value.
With no `GEMINI_API_KEY` set it returns a controlled `503
AI_EXPLANATION_UNAVAILABLE` and every finding stays fully usable. See
`../AI_EXPLANATION.md`.

See `MERGE_AUDIT.md` for how this repository was assembled (historical; paths in
it predate this workspace) and `../FINAL_AUDIT.md` for the current architecture.
