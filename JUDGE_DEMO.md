# JUDGE_DEMO.md

## 30-second pitch

Cryptiq turns real repository evidence into a role-aware post-quantum migration
review queue. It reads a repository at one exact commit, finds cryptographic
usage deterministically from the Python AST, quotes the exact line of source for
every finding, infers what each key is for, maps it to a post-quantum review
path, scores it for triage, and opens a review item — all reproducibly. AI only
explains a finding that already exists.

## 2-minute technical explanation

1. **Exact commit.** You give Cryptiq a GitHub URL and a 40-char SHA. It
   resolves and verifies that SHA through the GitHub API, downloads only that
   revision's archive (SSRF host allowlist, redirect-by-redirect validation,
   archive/size/file-count limits), extracts it to a temp dir that exists only
   for the duration of the analysis.
2. **AST analysis.** A Python AST parser builds call/import/scope context. No
   source is ever executed.
3. **Deterministic rules.** Rules for RSA, ECDSA, Ed25519, ECDH, X25519, AES and
   hashes recognise usage of the Python `cryptography` library from syntax
   alone. A construct is only reported when the AST establishes it. Output:
   `RuleMatch` — algorithm, API, operation, file, span, confidence, evidence
   basis.
4. **Evidence.** The exact source excerpt for that AST span is attached, with
   the rule id and parser/ruleset version stamps.
5. **Role.** A fixed table maps `(algorithm, operation)` to a cryptographic role
   (`DIGITAL_SIGNATURE`, `KEY_ESTABLISHMENT`, `SYMMETRIC_ENCRYPTION`, `HASH`,
   `UNKNOWN`) with a fixed rationale sentence. No model.
6. **PQC review path.** A fixed table maps `(algorithm family, role)` to a
   review path — `ML-DSA / SLH-DSA` for signatures, `ML-KEM` for key
   establishment, `KEY / IMPLEMENTATION REVIEW` for symmetric, `HASH / POLICY
   REVIEW` for hashes, `MANUAL REVIEW` otherwise — with a rationale and an
   `is_migration_candidate` flag (true only for the two public-key paths). This
   is a **review path, not a drop-in replacement**.
7. **Impact.** A bounded static chain: algorithm → API → function → class →
   module → file, within the scanned snapshot. Node ids are derived from node
   type + label, so the graph is stable across runs.
8. **Priority.** A fixed scorer produces a level, an integer score and a list of
   reason strings (e.g. "RSA is public-key cryptography broken by Shor's
   algorithm.", "SIGN operation.", "Blast radius spans 6 static elements."). It
   is a migration-review triage signal, not a CVE severity.
9. **Review queue.** Every migration candidate gets an `OPEN` review item when
   its scan completes. Reviewers move items `OPEN → IN_REVIEW → RESOLVED /
   ACCEPTED_RISK / FALSE_POSITIVE` via `PATCH /review-items/{id}`.
10. **Fingerprint + cache.** A finding's identity excludes line numbers and the
    commit SHA, so it survives an edit. A scan's identity is a 7-part tuple; an
    identical re-submit is served from stored findings with `cached: true` and no
    new work.
11. **AI explanation.** `POST /findings/{id}/explanation` sends one
    already-established finding (its deterministic facts + a bounded excerpt) to
    Gemini and returns a structured plain-language restatement, cached per
    finding fingerprint. The endpoint takes no request body. The model cannot
    change the algorithm, role, migration path, priority or source location, and
    deterministic fields are re-read from their own rows when rendered. With no
    key set it returns a controlled `503` and the finding is unaffected.

## 5-minute demo sequence

### Setup

```bash
# backend + in-process worker
cd cryptiq && source .venv/bin/activate
# optional, enables real AI explanations:
export GEMINI_API_KEY=your-key-here
RUN_WORKER=true uvicorn app.main:app --port 8000

# frontend (another terminal)
cd frontend && npm run dev            # http://localhost:5173
```

A completed scan of the acceptance commit is already persisted in
`cryptiq/cryptiq.db`, so the submit below returns instantly.

### Clicks

1. Open `http://localhost:5173` → **Inspect**.
2. Repository URL: `https://github.com/pyca/cryptography`
3. Commit SHA: `1f903f5ed2e5e316f345a927555e48535829d8de`
4. Click **Inspect Repository**.
5. On a fresh DB you would see **QUEUED → RUNNING** (polled every 2 s); with the
   persisted scan you land straight on the **Completed** report — 241 files,
   **1,042 findings**, 136 High / 906 Medium.
6. In the findings table, type **`RSA`** in "Filter by algorithm" → **34
   findings** (server-side `?algorithm=RSA`, page resets to 1).
7. Open the finding **RSA · DIGITAL_SIGNATURE · `tests/hazmat/primitives/test_rsa.py:2223`**.
8. Read the hero:
   - **RSA → Digital Signature** (`RSAPrivateKey.sign performs a sign operation.`)
   - **MIGRATION REVIEW PRIORITY: High**
   - **SOURCE EVIDENCE** — file, `Python · 1f903f5ed2`, line **2223**:
     `rsa_key_512.sign(b"somedata", padding.PKCS1v15(), hashes.SHA512())`
     (verbatim from GitHub at that commit — check it).
   - **IMPACT WITHIN SCANNED SCOPE** — RSA → RSAPrivateKey.sign →
     TestRSAEncryption.test_rsa_fips_small_key → TestRSAEncryption →
     tests.hazmat.primitives.test_rsa → the file (6 nodes).
   - **OBSERVED** (algorithm, API, repo, file, line, commit) vs **INFERRED**
     (role `DIGITAL_SIGNATURE`, confidence `HIGH`) vs **DIGITAL SIGNATURE ·
     REVIEW PATH** (`RSA → ML-DSA / SLH-DSA`, "Review against the FIPS 204
     (ML-DSA) and FIPS 205 (SLH-DSA) signature standards.").
9. Go to **Review**. The queue shows real migration candidates ordered by
   priority score, each with its reasons and review-path chip.
10. Open an **Open** item → **Start Review** (`OPEN → IN_REVIEW`, toast) →
    **Mark Resolved** (`IN_REVIEW → RESOLVED`, toast, "removed from active
    queue"). Re-open the finding: it shows **Resolved** — persisted.
11. Back on an RSA finding, click **Explain with AI**:
    - with `GEMINI_API_KEY` set: a structured explanation appears *below* the
      deterministic finding, labelled as subordinate; click again → served from
      cache (`cached: true`), no second model call.
    - without a key: "AI explanation unavailable for this finding." — the rest
      of the finding is intact.
12. Return to **Inspect** and submit the **same** repo + commit again → the
    completed report loads immediately (`POST /scans → 200 cached: true`), no
    re-scan.

### CLI equivalent

```bash
cd cryptiq && source .venv/bin/activate
python -m app.cli demo        # submit + poll + summarise the acceptance scan
python -m app.cli finding <finding_id>        # grouped Observed / Inference / Migration / Impact / Priority
```

## Key proof points

- **AI does not discover findings.** The `/explanation` endpoint takes no
  request body; the finding id is its whole input. A 1000-finding scan makes
  zero model calls.
- **Every finding has source evidence.** The excerpt is the exact AST span from
  the repository at the exact commit — verifiable against GitHub. `N/A` is shown
  where a value is genuinely absent; nothing is fabricated.
- **Role and PQC mapping are deterministic.** Fixed tables, fixed rationale
  strings, no scoring. `ECDSA + VERIFY → DIGITAL_SIGNATURE → ML-DSA / SLH-DSA`;
  `ECDH + KEY_ESTABLISHMENT → ML-KEM`.
- **Impact and priority are deterministic.** Node ids from type + label;
  priority from fixed tables with recorded reasons. Persisted node count matches
  the served `node_count`.
- **AI only explains an established finding.** Its reply is schema-validated to
  six explanatory strings; it cannot carry a deterministic value, and
  deterministic fields are re-read from their own rows at render time.
- **Repeated scans are cached.** Identical repo + commit → `cached: true`, no
  duplicate rows, stable fingerprints. See `CACHE_BEHAVIOR.md`.
