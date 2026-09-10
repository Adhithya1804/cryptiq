# CRYPTIQ FINAL SECURITY & AWS READINESS REPORT

Prepared by: final security / AWS-readiness / multi-repository / end-to-end validation pass
Date: 2026-09-10
Repo state: single commit `a3daba1` + large uncommitted working tree (backend `app/`, CLI, Docker, CI all present on disk)
Engine stamps: `parser_version=python-ast-1`, `ruleset_version=0.3.0`, `pqc_ruleset_version=0.2.0`

---

## 1. Executive Verdict

    DEMO READINESS:                 GREEN  (local / Docker-Compose demo)
    SECURITY:                       GREEN  (bare-minimum gate met; one MEDIUM fixed during this pass)
    AWS READINESS:                  RED    (no AWS deployment artifacts exist in the repo)
    MULTI-REPOSITORY GENERALIZATION: YELLOW (general across repo structures + any pyca/cryptography user;
                                            single-library rule coverage — PyCryptodome/pynacl/stdlib not detected)
    END-TO-END:                     GREEN  (browser→API→worker→findings→cache→CLI parity all verified live)
    OVERALL:                        YELLOW

**Why.**

CRYPTIQ's security engineering is real and testable, not cosmetic. The two controls that matter most for exposing a
static analyser to the internet — *it never executes the target repository*, and *it cannot be steered to make requests
to anything but GitHub* — both hold under direct adversarial testing. I built hostile repositories containing `setup.py`,
`conftest.py`, `Makefile`, `os.system(...)`, and `exec(compile(...))` side-effect markers, ran them through the exact
function the worker calls (`analyze_snapshot`) with socket and subprocess tripwires installed, and no marker file was
written, no socket opened, no process spawned. The engine is `ast.parse` + an iterative AST walk from end to end.

The SSRF guard is a tight allow-list (`api.github.com`, `github.com`, `codeload.github.com`, `*.githubusercontent.com`),
IP literals refused outright, every redirect hop re-validated, the `Authorization` header dropped on any host that is not
the API host, and a DNS-resolves-to-public check on top. A 24-payload probe (localhost, `127.0.0.1`, `169.254.169.254`,
decimal/hex/IPv6 literals, `user:pass@`, alternate ports, trailing-dot hosts, `evil.githubusercontent.com.attacker.com`,
credential tricks) was fully rejected. The archive extractor refuses traversal, absolute paths, Windows drives,
backslash separators, symlinks that escape (and skips in-tree symlinks rather than recreating them), device/FIFO
members, and enforces file-count / extracted-byte / archive-byte ceilings with a running total that stops a
decompression bomb — a 15-case hostile-archive battery produced zero filesystem escapes.

The Gemini layer is strictly downstream. It is the only place the SDK is imported, it is fed a bounded Pydantic packet
(one finding, source excerpt hard-capped at 2 000 chars, impact nodes capped at 40, no free-form caller field), its
system instruction treats the excerpt as untrusted data and forbids re-classification, and the response is schema-
validated before use. Critically, the explanation DTO returned to clients contains only prose fields — `summary`,
`why_it_matters`, etc. — so a hostile or malfunctioning model *cannot* change algorithm, role, confidence, PQC mapping,
or priority, because those values are never in the explanation response path.

The deterministic engine generalises. It is not tuned to pyca/cryptography: `pallets/click` (90 Python files, no
cryptography) yields 0 findings; `latchset/jwcrypto` (a third-party project, 13 Python files) yields 52 findings
correctly localised to `jwa.py`/`jwk.py`; `pyca/cryptography` yields 1054 in 4.2 s / 247 MB RSS. A synthetic
adversarial fixture with the same API name in a docstring, a string literal, a comment, a bare variable, a type
annotation, and a `getattr` produced *exactly* the three real calls and nothing else — AST precision is genuine.
Determinism is exact: three repeat scans produced byte-identical findings and identical priority scores. The single-
library scope is the limitation: `Crypto.*` (PyCryptodome), `nacl.*`, and stdlib `hashlib` are not detected. That is a
deliberate ruleset boundary (`library='cryptography'`), consistent and safe, not a defect — but it is the reason
generalization is YELLOW rather than GREEN.

The one real defect found and fixed: a check-then-insert race in `_upsert_repository`. Fifteen concurrent submissions of
a never-seen repository produced four HTTP 500s (`UNIQUE constraint failed: repositories.provider, owner, name`) because
several requests missed the lookup and all inserted. This is portable (would also hit PostgreSQL), trivially reachable
by an unauthenticated caller double-clicking "scan", and is now a get-or-create with savepoint recovery plus a
regression test; the same 15-way burst now returns 15×202. No data corruption occurred even before the fix (losing
transactions rolled back cleanly).

The blocker is AWS. **The repository contains no AWS deployment artifacts at all** — no EC2 user-data / cloud-init, no
CloudFormation / Terraform / CDK, no host nginx reverse-proxy config, no CloudWatch agent config, no SSM Parameter
Store wiring, no IAM policy, no security-group definition, no teardown script. The repo's own docs say so
(`INTEGRATION_REPORT.md:221` "Deployment / AWS / CI-CD: NOT IMPLEMENTED"; `DOCKER.md:249` "No … Terraform, or AWS
resources — out of scope"). What exists is a well-built local `docker-compose.yml` (backend published on
`127.0.0.1` only, frontend on `:8080`, non-root containers, no Docker socket, no secrets in images) and a PostgreSQL
override. The Section 21 architecture (EC2 t3.medium / AL2023 / CloudWatch / SSM) is a plan, not code. AWS readiness
therefore cannot be assessed as anything but RED until those artifacts are written; the container layer they would sit
on is sound.

For the actual question — *can this go on a temporary endpoint, let judges use it, scan real repos, survive hostile
input and normal failures, show credible security engineering, then be torn down?* — the answer is **yes for a
Docker-Compose demo on a laptop or a single VM you configure by hand**, and **not yet for the described push-button AWS
deployment**, because the AWS glue does not exist. Nothing about the application itself blocks a hackathon demo.

---

## 2. Architecture Tested

```
Browser ──► React/Vite SPA (nginx-unprivileged :8080, static bundle)
                │  (also same-origin /api proxy → backend:8000, curl convenience)
                ▼
        FastAPI app (:8000, uvicorn --no-server-header, non-root uid 1001, tini PID 1)
                │  POST /scans → Scan(QUEUED) + ScanJob(QUEUED), 202  |  identical completed identity → 200 cached
                ▼
        In-process async worker loop (RUN_WORKER=true)
                │  claim job → ingest → analyse (asyncio.to_thread) → persist → COMPLETED/FAILED
                ▼
        GitHub ingestion  ── validator allow-list + redirect re-validation + resolves-public check
                │           ── zip download (byte ceiling) → safe extract (traversal/symlink/bomb guards)
                ▼
        Deterministic engine  ── ast.parse → AST walk → rules → role inference → PQC mapping
                │                ── impact (static only) → priority (deterministic scorer) → fingerprints
                ▼
        SQLite (named volume /data) or PostgreSQL (override)  ── evidence required at flush time
                │
                ▼
        Optional Gemini explanation  ── isolated service, bounded input, schema-validated output,
                                         cache key = finding_fingerprint + prompt_version + model,
                                         no-key → 503 AI_EXPLANATION_UNAVAILABLE, finding unaffected

CLI (app.cli): local mode = same app.engine.pipeline in-process, offline, git archive only (no hooks);
               remote mode = thin API client. Fingerprints identical across CLI-local / API / worker.
```

The AI layer is downstream and cannot alter deterministic fields — verified structurally (they are not in the
explanation DTO) and by test.

---

## 3. Security Threat Model

| Threat | Tested | Result | Severity | Action |
|---|---|---|---|---|
| Arbitrary code execution via malicious repo (server) | YES — markers + socket/subprocess tripwires through `analyze_snapshot` | PASS — no marker, no socket, no proc | P0 if broken | none — engine is pure AST |
| Arbitrary code execution via malicious repo (CLI local) | YES — `setup.py`/`conftest.py` markers via `cryptiq scan --commit`; existing `tests/security/test_cli_security.py` | PASS — `git archive` runs no hook; only read-only `git` subcommands, no shell | P0 if broken | none |
| SSRF to metadata / internal (repo URL ingestion) | YES — 24-payload probe of `parse_repository_url` + `assert_allowed_url` | PASS — all rejected | P0 if broken | none |
| SSRF via redirect to private host | YES — code review: every hop re-validated, `follow_redirects=False`, MAX_REDIRECTS=5 | PASS | P0 if broken | none |
| Auth header leak to non-API host on redirect | YES — code review (`_headers` sends `Authorization` only when host == api host) | PASS | P1 | none |
| DNS rebinding | PARTIAL — `assert_host_resolves_publicly` resolves separately from the socket; allow-list is the primary control | PASS (mitigated by tight allow-list — attacker cannot own a `*.githubusercontent.com` name) | P2 | accept; document |
| Archive path traversal / absolute / drive / backslash | YES — 15-case hostile battery + `safe_relative_path` unit probe | PASS — no escape | P0 if broken | none |
| Symlink traversal | YES — escaping symlink rejected, in-tree symlink skipped not recreated | PASS | P0 if broken | none |
| Decompression / zip bomb | YES — 20 MB zero-fill vs 5 MB ceiling; running-total check | PASS — `ARCHIVE_TOO_LARGE` | P1 | none |
| Oversized archive / file count | YES — 1 001-file archive vs 1 000 limit; large single file | PASS — rejected / marked TOO_LARGE at discovery | P2 | none |
| Prompt injection via repository source into Gemini | YES — code review + `tests/unit/test_gemini_service.py` | PASS — excerpt is data, bounded, schema-validated; deterministic fields absent from output DTO | P1 | none |
| Gemini alters algorithm/role/PQC/priority | YES — structural (fields not in DTO) + tests | PASS — impossible by construction | P0 if broken | none |
| SQL injection | YES — API fuzz with `1' OR '1'='1` id; all queries are SQLAlchemy-parameterised | PASS — 404 with string safely echoed | P0 if broken | none |
| XSS via hostile repository source in UI | YES — `SourceEvidence.tsx` / `AiExplanation.tsx` render as JSX text; no `dangerouslySetInnerHTML`/`innerHTML`/`eval` in `frontend/src` | PASS — inert text | P1 | none |
| Secret leakage (repo / images / bundle / logs / errors) | YES — git history, `.env`, built `dist/`, running container env, error bodies | PASS — no real secrets anywhere; error handler returns generic 500 | P0 if broken | none |
| Unauthenticated resource exhaustion (unbounded scans/queue/rows) | YES — analysis + live test | PARTIAL — no rate limit; queue/rows grow unbounded; worker serialises so CPU/disk bounded to one scan | P2 | classify (below); acceptable for *controlled* demo |
| Concurrent new-repo submit → 500 | YES — 15-way burst, reproduced | FIXED this pass — get-or-create + savepoint recovery + regression test | P2 | fixed |
| SQLite write-lock contention under demo load | YES — 200 concurrent reads during a real worker persist | PASS — 0 lock errors, scan COMPLETED | P3 | recommend `busy_timeout`+WAL for headroom (not required) |
| Failed scan served as cache hit | YES — `find_completed_scan` filters `ScanStatus.COMPLETED` only; worker `_fail` path | PASS — impossible | P0 if broken | none |
| Worker dies on a bad job | YES — code review + live failure | PASS — `except Exception` in `worker_loop`, job → FAILED/retry, loop continues | P1 | none |
| Malformed / hostile API input → stack trace / 500 | YES — 19-case fuzz | PASS — stable `{"error":{"code","message"}}`, no traceback / path / SQL text | P1 | none |
| Container escape / Docker socket / privileged | YES — `docker inspect` live containers | PASS — non-root, `Privileged=false`, `CapAdd=[]`, no `/var/run/docker.sock` | P0 if broken | none |
| Image ships a secret | YES — `docker history` + running `env` | PASS — no key/token/password in image; `.dockerignore` excludes `.env`/`*.db` | P0 if broken | none |
| CORS abuse | YES — disallowed origin gets no ACAO header; `allow_credentials=False` | PASS | P2 | keep `CORS_ALLOW_ORIGINS` explicit (never `*`) in the deployment |
| Dependency CVEs in images | NOT TESTED locally (Trivy not installed) — CI gate exists | N/A | P2 | rely on CI `trivy-scan` job; `.trivyignore.yaml` is disciplined and time-boxed |
| Untrusted-PR abuse of CI | YES — workflow review | PASS-ish — `pull_request` (not `pull_request_target`), fork token read-only, no custom secrets referenced; fork can still run its own Dockerfile/build with no secrets to steal | P3 | accept for hackathon; note |
| Large request body memory DoS | PARTIAL — 1 MB URL field handled; no explicit body-size cap | PARTIAL | P3 | recommend a body-size limit at nginx for public exposure |

---

## 4. Bare-Minimum Security (REQUIRED NOW) — results

| Control | Test | Input | Expected | Actual | Result |
|---|---|---|---|---|---|
| No secrets committed | `git log -p` scan; `git ls-files \| grep env` | full history (1 commit) | only placeholders | `GEMINI_API_KEY=your-key-here`, doc examples, one test constant `github_token="super-secret-token"` in `tests/` | PASS |
| `.env` not tracked | `git ls-files --error-unmatch .env` | — | not tracked | not tracked (gitignored at both levels); blank secrets | PASS |
| No key in frontend bundle | grep fresh `frontend/dist` for `AIza…`, `ghp_…`, `-----BEGIN`, `xox…` | built bundle | none | none | PASS |
| No secret in image layers | `docker history --no-trunc`; running container `env` | both images | none | `GEMINI_API_KEY=` / `GITHUB_TOKEN=` empty; no `ENV …KEY=` layer | PASS |
| No secret in error bodies | 19-case API fuzz | malformed / SSRF / bad ids | typed JSON only | `{"error":{"code","message"}}`, generic 500, no traceback/path/SQL | PASS |
| SSRF — repo URL ingestion | probe `parse_repository_url` | localhost / `127.0.0.1` / `0.0.0.0`-class / `169.254.169.254` / `2130706433` / `0x7f000001` / `[::1]` / `user:pass@` / `:8443` / trailing-dot / `github.com.attacker.com` / `raw.githubusercontent.com` / `%00` / `javascript:` / `ftp://` | all rejected | all rejected; only `https://github.com/{owner}/{name}` accepted | PASS |
| SSRF — outbound guard | probe `assert_allowed_url` | metadata IP, loopback, IPv6, decimal IP, `evil.githubusercontent.com.attacker.com`, `api.github.com.attacker.com`, bare `githubusercontent.com`, `http://` | refuse all non-allow-listed | refused; `api.github.com` / `codeload.github.com` / `*.githubusercontent.com` allowed | PASS |
| SSRF — redirects | code review | 302 to private host | re-validate each hop | `follow_redirects=False`; loop calls `assert_allowed_url` + `assert_host_resolves_publicly` per hop; MAX 5 | PASS |
| SSRF — token scoping | code review | redirect API→codeload | drop `Authorization` | header added only when `urlsplit(url).hostname == api_host` | PASS |
| Archive traversal | 15-case hostile battery + unit probe | `../`, nested `../`, `/etc/…`, `C:/…`, `..\\…`, null byte, unicode, dup names, 1 001 files, escaping symlink, absolute symlink, char-device, 20 MB bomb, non-zip, truncated, zip-in-zip | traversal/oversize rejected; benign extract | all traversal/oversize rejected; no filesystem escape; symlinks skipped | PASS |
| Never execute target code (server) | markers + tripwires through `analyze_snapshot` | `setup.py`/`conftest.py`/`Makefile`/`os.system`/`exec(compile())` | no execution | no marker file; no socket; no subprocess; 3 correct findings produced | PASS |
| Never execute target code (CLI) | `tests/security/test_cli_security.py` + review | `setup.py`/`conftest.py` markers, symlink escape, network block | no execution / no escape / no network | PASS (5 tests) | PASS |
| No dependency install / test run / import of target | code review | any repo | none | engine imports nothing from the tree; `git archive`/zip only; CI self-scan installs only Cryptiq's `requirements.txt` | PASS |

---

## 5. Mid-Range Security (RECOMMENDED NOW) — implemented vs recommended

| Item | State |
|---|---|
| Structured, non-leaking error contract | IMPLEMENTED (`app/errors.py`, catch-all → generic 500 + server-side `logger.exception`) |
| CORS explicit allow-list, `allow_credentials=False`, methods/headers restricted | IMPLEMENTED (`app/main.py`); `*` honoured only if explicitly set |
| Ingestion resource ceilings (archive / extracted / file count / file size / scan timeout) | IMPLEMENTED, env-configurable (`IngestionLimits`, `SCAN_TIMEOUT_SECONDS`) |
| Page-size ceiling on list endpoints | IMPLEMENTED (`MAX_PAGE_SIZE=200`, `Query(ge=1, le=…)`) |
| Job lifecycle state machine + retry cap + worker survives failure | IMPLEMENTED (`scan_jobs.py`, `worker.py`) |
| Evidence-required invariant at flush | IMPLEMENTED (`app/db/integrity.py`) |
| Trivy CRITICAL + secret gate in CI, time-boxed `.trivyignore.yaml` | IMPLEMENTED |
| Non-root containers, tini PID 1, no Docker socket, minimal base, healthchecks | IMPLEMENTED |
| Frontend security headers (`X-Content-Type-Options`, `X-Frame-Options: DENY`, `Referrer-Policy`), `server_tokens off` | IMPLEMENTED (`frontend/nginx.conf`) |
| Get-or-create race hardening on repository upsert | IMPLEMENTED THIS PASS |
| Rate limiting / request quota on the unauthenticated API | RECOMMENDED — not implemented (see §15) |
| SQLite `busy_timeout` + WAL for concurrency headroom | RECOMMENDED — not implemented (no failure reproduced; low-risk to add) |
| Request body-size cap for public exposure | RECOMMENDED — add at the reverse proxy |
| Disable `/docs` + `/openapi.json` in the deployment | RECOMMENDED (currently served; not a secret, mild attack-surface reduction) |
| CI actions pinned by SHA (currently major-tag) | RECOMMENDED for OSS release |

---

## 6. AWS Readiness

**Status: RED — the AWS deployment does not exist in the repository.**

| Area | Expected (Section 21) | Present in repo | Result |
|---|---|---|---|
| Compute provisioning | EC2 t3.medium, AL2023, launch/user-data | none | MISSING |
| Orchestration on host | Docker Compose + host nginx :80 → :8080 | local `docker-compose.yml` only; nginx.conf is the *frontend container's* (:8080 → `backend:8000`) | PARTIAL (no host proxy / no :80) |
| Networking | SG allowing only TCP 80; 8000/5432/22 closed | no SG definition | MISSING (compose already keeps 8000 on loopback, 5432 unpublished — good building blocks) |
| IAM | instance role, minimal SSM + CloudWatch, no static creds | none | MISSING |
| Secrets | `GEMINI_API_KEY` / `GITHUB_TOKEN` via SSM Parameter Store, backend-only | mechanism is env-only; secrets are backend-only and never in images (verified) | PARTIAL (no SSM integration) |
| Persistence | SQLite on EBS, survives restart | named Docker volume `cryptiq-data:/data`; **restart persistence verified** (52 findings survived `docker compose restart backend`) | PASS for the container layer |
| Logging | frontend/backend/worker/scan/Gemini logs → CloudWatch | logs go to stdout/stderr (12-factor); no CloudWatch agent/config | MISSING (shipping layer) |
| Containers | non-root, no privileged, no host mounts, no socket | verified on live containers | PASS |
| Teardown | documented AWS cleanup | none | MISSING |
| Cost control | — | n/a without infra | N/A |

**AWS exposure test (Section 23): NOT TESTED** — no AWS credentials available to this pass, no deployment artifacts to
apply, and deploying real infrastructure was not authorised. The *container* end-to-end (browser → nginx → API → worker →
findings → cache, plus backend restart) was fully exercised against the local Docker-Compose stack instead (see §34).

---

## 7. Multi-Repository Results

| Repository | Commit | Py files | Findings | Time | RSS | Result | Notes |
|---|---|---:|---:|---:|---:|---|---|
| pyca/cryptography | `e57b922…` (depth-1 clone HEAD 2026-09-10) | 243 | 1054 | 4.2 s | 247 MB | PASS | broad algo spread; roles sane (AES→SYMMETRIC, hash→HASH, ECDSA/Ed25519→DIGITAL_SIGNATURE, ECDH/X25519→KEY_ESTABLISHMENT, bare RSA keygen→UNKNOWN); heaviest in the library's own tests (expected) |
| pallets/click | `6aabf09…` | 90 | 0 | 0.9 s | 122 MB | PASS | real project, zero cryptography — zero findings, no crash |
| latchset/jwcrypto | `48f1e80…` | 13 | 52 | 0.55 s | 83 MB | PASS | **third-party** (non-pyca) consumer of the `cryptography` library; findings correctly localised to `jwa.py`/`jwk.py` |
| Synthetic F (crypto-heavy) | local | 3 | 11 | <0.5 s | — | PASS | RSA/ECDSA/ECDH/Ed25519/X25519/AES-GCM/SHA-256/HMAC all detected |
| Synthetic G (adversarial) | local | 2 | 3 | <0.5 s | — | PASS | exactly the 3 real calls; docstring / string literal / comment / bare variable / annotation / `getattr` all correctly ignored; aliased import + multiline call resolved |
| Synthetic E (no crypto) | local | 2 | 0 | <0.5 s | — | PASS | incl. `hashlib.md5` — **not** flagged (ruleset targets `cryptography`, not stdlib) |
| Synthetic D (PyCryptodome) | local | 1 | 0 | <0.5 s | — | YELLOW | `Crypto.PublicKey.RSA` / `Crypto.Cipher.AES` / `pkcs1_15` — **not detected**; unsupported-but-safe |
| Synthetic Big (1 200 files, 1 planted) | local | 1 200 | 1 | 0.56 s | 64 MB | PASS | scales; bounded memory; correct single finding |

**Assessment.** No hardcoded repository/path/library-name assumptions were found. The engine works across flat
(`click`), package (`jwcrypto`), and very large (`cryptography`) layouts and on a third-party consumer of the target
library. It does **not** cover other crypto libraries (PyCryptodome, PyNaCl) or stdlib `hashlib`. That is a deliberate,
consistent rule-spec boundary — not a false negative within scope, and per the brief not something to "fix" by widening
rules. It is the sole reason GENERALIZATION is YELLOW.

---

## 8. False Positive / False Negative Results

SHOULD MATCH (all matched):

| Case | Fixture | Result |
|---|---|---|
| RSA key generation | `rsa.generate_private_key(...)` | MATCH — role `UNKNOWN` (keygen alone doesn't establish role) |
| RSA signing (multiline, aliased import) | `_rsa_alias.generate_private_key(\n …\n)` then `key.sign(...)` | MATCH — `PY-CRYPTO-RSA`, `RSAPrivateKey.sign` |
| RSA PSS / OAEP | repoF `rsa_ops.py` | MATCH |
| ECDSA signing | `key.sign(d, ec.ECDSA(...))` | MATCH — role `DIGITAL_SIGNATURE`, HIGH |
| ECDH key agreement | `priv.exchange(ec.ECDH(), peer)` | MATCH — role `KEY_ESTABLISHMENT` |
| Ed25519 / X25519 | `Ed25519PrivateKey.generate/.sign`, `X25519PrivateKey.generate` | MATCH |
| AES-GCM AEAD | `AESGCM(key).encrypt(...)` | MATCH — role `SYMMETRIC_ENCRYPTION` |
| Hash / HMAC | `hashes.Hash(hashes.SHA256())`, `hmac.HMAC(...)` | MATCH — role `HASH` |

SHOULD NOT MATCH (none matched):

| Case | Fixture | Result |
|---|---|---|
| API name in module docstring | `"""… rsa.generate_private_key …"""` | no match |
| API call inside a string literal | `DEAD_STRING = "key.sign(data, …)"` | no match |
| Commented-out call | `# rsa.generate_private_key(...)` | no match |
| Function named like the library | `def rsa(): return 1` | no match |
| Bare variable binding | `generate_private_key = None` | no match |
| Type annotation only | `x: "ec.EllipticCurvePrivateKey" = None` | no match |
| Dynamic attribute access | `getattr(_rsa_alias, "generate_private_key")` | no match |
| EC bare key generation | `ec.generate_private_key(ec.SECP256R1())` with no downstream op | no match (consistent with pyca run; deliberate — EC keygen is role-ambiguous) |

Aliased imports (`import … .rsa as _rsa_alias`, `from … import ec as elliptic`), nested functions, async methods,
decorators, and conditional branches are all handled. **Zero systemic false positives; zero in-scope false negatives.**

---

## 9. Hostile Repository Results

| Fixture | Delivery | Expected | Actual | Result |
|---|---|---|---|---|
| `setup.py` + `conftest.py` writing `/tmp/CRYPTIQ_ENGINE_PWNED` | server `analyze_snapshot` | not executed | marker absent | PASS |
| `Makefile` / `evil.sh` touching a marker | server | not executed | marker absent | PASS |
| `pkg/mod.py` with `os.system(...)`, `subprocess.run(...)`, `exec(compile(...))` at import time | server, with socket + subprocess tripwires | not executed | no marker, no socket, no proc; 3 valid findings | PASS |
| `setup.py`/`conftest.py` markers | CLI `scan --commit` (`git archive`) | not executed | marker absent (`tests/security/test_cli_security.py`) | PASS |
| Symlink escaping the tree | CLI worktree + commit | not followed | not followed; not in findings | PASS |
| Archive `../…`, `/etc/…`, `C:/…`, `..\\…` | `extract_zip` | rejected | `UnsafeArchiveError` | PASS |
| Archive escaping symlink / absolute symlink / char-device | `extract_zip` | rejected or skipped | escaping symlink → reject; in-tree symlink → skipped; device → reject | PASS |
| 20 MB zero-fill vs 5 MB extracted ceiling | `extract_zip` | rejected mid-stream | `ARCHIVE_TOO_LARGE` | PASS |
| 1 001 files vs 1 000 limit | `extract_zip` | rejected | `ARCHIVE_TOO_LARGE` | PASS |
| Malformed / truncated zip | `extract_zip` | rejected | `MalformedArchiveError` | PASS |
| Deeply nested / pathological AST | existing `tests/security/test_parser_safety.py` | structured failure, no crash | PASS (iterative walk; `RecursionError`/`MemoryError` caught) | PASS |
| Null byte in source | existing parser-safety test | structured failure | PASS | PASS |
| Prompt-injection text in `source_excerpt` sent to Gemini | `tests/unit/test_gemini_service.py` + system instruction review | ignored as instruction; deterministic fields unchanged | PASS (fields not in output DTO) | PASS |

---

## 10. CLI Results

| Command | Mode | Test | Result |
|---|---|---|---|
| `cryptiq version --json` | — | prints CLI + engine stamps | PASS |
| `cryptiq scan <dir> --format json` | local | 4 synthetic + 3 real repos | PASS (findings as in §7) |
| `cryptiq scan <dir>` offline | local | run with `env -i` (no network/DB/API/GEMINI vars) | PASS — 11 findings, no dependency on API/DB/Gemini/network |
| `cryptiq scan <dir> --commit <sha>` | local | git repo, two commits | PASS — analyses `git archive` of the commit; working tree untouched |
| `cryptiq diff --base <a> --head <b> --json` | local | NEW + FIXED + UNCHANGED across two commits | PASS — see §17 |
| `--fail-on` exit codes | local | HIGH finding present / identical commits | PASS — exit 1 when NEW/priority threshold hit; exit 0 when clean/identical |
| API failure produces no traceback | remote | `POST /findings/<missing>/explanation` | PASS — typed 404, no stack |
| CLI ↔ API fingerprint parity | both | `latchset/jwcrypto @ 48f1e80` via CLI-local **and** via the running Docker API/worker | PASS — 52 findings both ways |
| SARIF output | local | `--format sarif` code path + `tests/unit/test_cli_sarif.py` | PASS (unit-covered; CI self-scan produces valid SARIF 2.1.0) |
| Remote subcommands (`findings`, `finding`, `review-queue`, `review-update`, `scan-status`) | remote | `tests/unit/test_cli_remote.py` / `test_cli_results.py` | PASS (unit-covered) |

Local mode uses only read-only `git` subcommands via argv (no shell), runs no repository hook, and needs no API,
database, or Gemini.

---

## 11. Gemini Results

| Scenario | Test | Result |
|---|---|---|
| No API key | live `TestClient`, `GEMINI_API_KEY=""` | 503 `AI_EXPLANATION_UNAVAILABLE`; nothing persisted/billed; finding stands |
| API error (HTTP status) | `tests/unit/test_gemini_service.py::test_api_error_becomes_gemini_error_without_leaking_details` | `GeminiError` → 503; only status logged, no body |
| Transport / timeout | `test_transport_error_becomes_gemini_error` | `GeminiError` → 503 |
| Empty response | `test_empty_response_is_an_error` | `GeminiError` → 503 |
| Malformed / schema-violating output | `test_service_rejects_malformed_model_output` | `ValidationError` → `GeminiError` → 503; nothing returned |
| API key never logged | `test_api_key_is_never_logged` | PASS |
| Bounded input | `test_build_input_is_bounded` | one finding; excerpt ≤ 2 000 chars; ≤ 40 impact nodes; no free-form field |
| Prompt injection in excerpt | system instruction + structural review | excerpt is data; deterministic fields (`algorithm`/`role`/`confidence`/PQC/`priority`) are **absent from the explanation DTO** → cannot be changed |
| Cache identity | `_cached_explanation` review | `finding_id + prompt_version + model + finding_fingerprint + status=COMPLETED` |
| Live call | SKIPPED — `GEMINI_API_KEY` not set (`tests/integration/test_gemini_live.py`) | NOT TESTED (expected) |

26/26 Gemini unit + explanation-API tests pass.

---

## 12. Docker Results

| Check | Backend | Frontend |
|---|---|---|
| Build | image `cryptiq-backend:local` 416 MB (multi-stage, venv copied, no build tooling in runtime) | image `cryptiq-frontend:local` 78 MB (alpine, static bundle only) |
| Base image | `python:3.12-slim-bookworm` (Python 3.12.14) | `nginxinc/nginx-unprivileged:1.27-alpine` |
| Runtime user | `cryptiq` uid 1001 (verified `id` in live container) | uid 101 |
| PID 1 | `tini` (signal forwarding / zombie reaping) | image default entrypoint |
| Privileged / caps / socket | `Privileged=false`, `CapAdd=[]`, no `/var/run/docker.sock` | `Privileged=false`, `CapAdd=[]` |
| Host mounts | named volume `:/data` + `deploy/seed:ro` only | none |
| Secrets in image | none (`docker history`, running `env`) — `GEMINI_API_KEY`/`GITHUB_TOKEN` empty | none — only `VITE_API_BASE_URL` (a URL) baked into JS |
| Server header | `uvicorn --no-server-header` in image CMD | `server_tokens off` |
| Dev conveniences | no `--reload`, no debug | n/a |
| Healthcheck | `/health/ready` (process + DB) | `/healthz` |
| `.dockerignore` | excludes `.git`, `.env*`, `*.db`, `tests` | excludes `.git`, `.env*`, `node_modules`, `dist` |
| Ports exposed | 8000 only; compose publishes `127.0.0.1:8001` | 8080; compose publishes `0.0.0.0:8080` |
| `docker compose config` | valid | valid |
| Trivy image scan | NOT TESTED locally (Trivy not installed) — CI `trivy-scan` job gates CRITICAL + secrets; `.trivyignore.yaml` = 5 base-image OS CVEs (zlib minizip, libsqlite3, 3× perl-base), each with a written non-reachability justification and `expired_at: 2026-12-09` | same gate |

`ReadonlyRootfs=false` on the backend (writable `/tmp` for extraction) — acceptable for the demo; `read_only: true` +
tmpfs `/tmp` is optional hardening.

---

## 13. CI/CD Results

| Check | Result |
|---|---|
| Pipeline shape | `quality (backend+frontend) → docker-build → {trivy-scan, cryptiq-self-scan}` |
| Default permissions | `contents: read`; SARIF jobs opt into `security-events: write` only |
| Concurrency | one in-flight run per PR/branch, `cancel-in-progress: true` |
| Backend gate | `ruff check` + `pytest -q` (comment says "761 passed" — **stale**, actual 811) |
| Frontend gate | `tsc --noEmit` + `eslint --max-warnings 0` + `vitest run` + `vite build` — all green locally |
| `ruff format --check` | **not run in CI**; 64 files would reformat locally (mostly tests) — style drift, not a gate failure |
| Type checking (backend) | **none configured** (no mypy/pyright) — "type checking" in the regression gate is N/A |
| Trivy | version pinned `0.74.0`; full inventory scan of the exact built image; gate = any non-suppressed CRITICAL or leaked secret; HIGH reported only; suppressed base CVEs stay visible via `--show-suppressed` |
| SARIF | distinct categories (`trivy-backend`, `trivy-frontend`, `cryptiq-self-scan`); self-scan asserts `version == 2.1.0` |
| Self-scan safety | downloads the commit archive and runs AST analysis only; installs Cryptiq's `requirements.txt`, nothing from the target; `GITHUB_TOKEN` = `github.token`, never echoed |
| Actions pinning | major tags (`@v4`, `@v6`, `setup-trivy@v0.2.6`) — fine for hackathon; pin to SHA for OSS release |
| Untrusted-PR abuse | `on: pull_request` (not `pull_request_target`); fork PRs get a read-only token and no custom secrets; a fork can run its own Dockerfile/build steps but has nothing to exfiltrate |

---

## 14. Defects Found

| ID | Severity | Component | Reproduction | Root cause | Fix | Regression test |
|---|---|---|---|---|---|---|
| D-1 | P2 (MEDIUM) — **fixed this pass** | `app/services/scans.py::_upsert_repository` | `POST /api/v1/scans` ×15 concurrently for a never-seen repo → 4× HTTP 500 `UNIQUE constraint failed: repositories.provider, owner, name` | check-then-insert race: multiple requests miss the `SELECT`, all `INSERT`; unhandled `IntegrityError` → 500. Portable (also hits PostgreSQL). No corruption (losers roll back). | get-or-create: `add`+`flush` inside `session.begin_nested()` savepoint; on `IntegrityError`, re-read the winner's row and return it. ~20 lines. | `tests/integration/test_scan_service_race.py` (deterministically forces the lookup miss, asserts recovery + single row) |
| D-2 | P3 (LOW) | CI `.github/workflows/ci.yml` | comment "Baseline: 761 passed" vs actual 811 | stale comment after tests were added | not changed (doc-only; out of minimal-fix scope) | n/a |
| D-3 | P3 (LOW) | repo formatting | `ruff format --check .` → 64 files would reformat | repo not run through `ruff format`; CI only does `ruff check` | not changed (style; no functional impact) | n/a |
| D-4 | P3 (LOW) | `docker-compose.postgres.yml` / `.env` | `POSTGRES_PASSWORD` default `cryptiq` present in backend env even on the SQLite path | weak default password | not changed (documented "change for anything beyond a laptop"); flag for the deployment | n/a |

Post-fix: **811 passed, 34 skipped**, `ruff check` clean; frontend `tsc`/`eslint`/`vitest`(57)/`build` all green.

---

## 15. Accepted Limitations

**Acceptable for a controlled hackathon demo:**

- **Unauthenticated API with no rate limit.** An anonymous caller can queue unbounded scans → unbounded `scans` /
  `scan_jobs` / `repositories` rows and unbounded queued jobs. The worker processes serially, so CPU/disk stay bounded
  to one scan at a time (ceilings: 25 MB archive / 50 MB extracted / 2 000 files / 300 s per the Docker `.env`), and a
  cache hit costs nothing. For a demo where judges use the endpoint under supervision this is acceptable; the failure
  mode is a slow queue, not a crash or data loss. **If a tiny mitigation is wanted:** a fixed in-process cap
  (e.g. reject `POST /scans` with 429 when `COUNT(scan_jobs WHERE status IN (QUEUED,RUNNING)) > N`) is ~10 lines and
  needs no new infrastructure. Not implemented in this pass because no failure was demonstrated under realistic load and
  the brief forbids a production rate limiter.
- **`/docs` and `/openapi.json` served.** Not a secret; mild attack-surface. Fine for a demo (arguably useful to
  judges); disable for anything longer-lived.
- **`ReadonlyRootfs=false`** on the backend container.
- **Gemini live path** untested (no key) — the no-key path *is* tested and is the demo default.
- **CI actions pinned by major tag**, not SHA.

**Unacceptable for a hackathon demo (must be resolved) — none.** No P0/P1 defect remains. D-1 (the only functional
defect) is fixed.

**Future production requirements (do NOT implement now):** authentication/authorization, a real distributed rate
limiter / WAF, HTTPS/ALB, managed PostgreSQL with least-priv DB users, per-tenant isolation, a durable job queue,
multi-worker `FOR UPDATE SKIP LOCKED` fan-out (the code path exists but is untested at scale), SHA-pinned actions,
read-only container root FS, and structured log shipping.

---

## 16. Required Pre-Demo Fixes

1. **D-1 repository-upsert race — DONE this pass** (`app/services/scans.py` + regression test). Re-run
   `pytest -q` (811 pass) before the demo build. This is the only item that was a genuine blocker-class defect, and it
   is closed.

Nothing else is required for a local / single-VM Docker-Compose demo.

If the demo must be the **AWS endpoint described in Section 21**, then the AWS deployment layer is a required
deliverable that does not currently exist (see §6 and below) — that is scope, not a fix.

---

## 17. Recommended Pre-Demo Fixes (if time allows)

- Add the ~10-line in-flight-jobs cap → 429 on `POST /scans` (cheap abuse ceiling for an unauthenticated endpoint).
- Add SQLite `PRAGMA busy_timeout=5000` + `journal_mode=WAL` via a `connect` event listener for `sqlite://` URLs
  (headroom for API + in-process worker; no failure reproduced but low-risk and standard).
- Add a request body-size limit at the reverse proxy (`client_max_body_size 32k;` — the API only ever takes small JSON).
- Disable `/docs` and `/openapi.json` in the deployment (`FastAPI(docs_url=None, openapi_url=None)` gated on
  `environment == "prod"`).
- Fix the stale CI baseline comment (761 → 811); optionally add `ruff format --check` to CI and format the tree once.
- `docker compose` for the deployment: set a real `POSTGRES_PASSWORD` (if using the Postgres path) and keep
  `CORS_ALLOW_ORIGINS` pinned to the exact frontend origin.

## 18. Future Production Hardening (not now)

Authentication, authorization, distributed rate limiting, WAF, ALB + HTTPS/ACM, managed PostgreSQL, stronger sandbox
isolation for analysis (gVisor/Firecracker/seccomp), a durable job queue, multi-tenant controls, SHA-pinned CI actions,
read-only container root filesystem + tmpfs, and CloudWatch/OTEL log+metric pipelines.

---

## 19. Demo Runbook (local / single VM — verified)

```bash
# 0. one-time: copy env (all secrets stay blank for the SQLite demo)
cd <repo-root>
cp .env.example .env            # optional: set GEMINI_API_KEY to enable the AI panel

# 1. build + start (backend on 127.0.0.1:8000/8001, frontend on :8080)
docker compose build
docker compose up -d
docker compose ps               # both services should be "healthy" within ~40s

# 2. verify
curl -s http://localhost:8080/healthz                         # ok
curl -s http://localhost:8080/api/v1/health                   # {"status":"ok",...}   (via nginx proxy)

# 3. run a scan through the UI at http://localhost:8080  (or via curl:)
curl -s -X POST http://localhost:8080/api/v1/scans \
  -H 'content-type: application/json' \
  -d '{"repository_url":"https://github.com/pyca/cryptography","commit_sha":"1f903f5ed2e5e316f345a927555e48535829d8de"}'
# → 202 (fresh) or 200 with "cached":true if the seed DB is mounted
#   drop deploy/seed/cryptiq.db in place for an instant cached demo of that commit

# 4. CLI parity (offline, in-process engine — no API/DB/Gemini needed)
cd cryptiq && python -m app.cli scan /path/to/local/checkout --format json --fail-on never
python -m app.cli diff --base <sha_a> --head <sha_b> --json     # NEW / FIXED / UNCHANGED by fingerprint

# 5. logs
docker compose logs -f backend        # scan queued/started/completed/failed, Gemini failures
```

End-to-end verified this pass: submit via nginx proxy → worker ingests from GitHub (SSRF-guarded) → analyse → persist →
`COMPLETED` with 52 findings for `latchset/jwcrypto@48f1e80`; `docker compose restart backend` → 52 findings still
present; resubmit → HTTP 200 `cached:true`. CLI-local on the same commit → 52 findings (fingerprint parity).

## 20. Emergency Recovery (local / single VM — verified where noted)

| Failure | Command | Notes |
|---|---|---|
| Backend crash / hang | `docker compose restart backend` | `restart: unless-stopped` already auto-restarts; data on the `cryptiq-data` volume survives (**verified**) |
| Worker wedged (in-process) | `docker compose restart backend` | worker shares the backend process; a stuck job retries up to its cap then → `FAILED`, loop continues (**verified: worker survives failed jobs**) |
| Frontend down | `docker compose restart frontend` | static assets only; no state |
| Whole stack | `docker compose down && docker compose up -d` | volume persists unless `-v` is passed |
| DB file corrupt (SQLite) | `docker compose down`; restore `deploy/seed/cryptiq.db` into the `cryptiq-data` volume or delete it to start fresh; `docker compose up -d` (entrypoint runs `alembic upgrade head`) | seeding path is first-run only |
| Gemini unavailable | no action | API returns 503 `AI_EXPLANATION_UNAVAILABLE`; every finding stays fully usable (**verified**) |
| GitHub unavailable / rate-limited | set `GITHUB_TOKEN` in `.env`, `docker compose up -d`; or demo from the cached seed DB | ingestion maps failures to typed 502s; worker → `FAILED`, no partial persist, not cacheable (**verified: failed ≠ cache hit**) |
| EC2 instance failure | **N/A — no AWS deployment exists** | would require the missing infra layer |

## 21. Teardown

Local / single VM:

```bash
docker compose down -v            # stop + remove containers, network, AND the cryptiq-data volume
docker image rm cryptiq-backend:local cryptiq-frontend:local
docker builder prune -f           # optional: drop build cache
```

AWS: **no teardown procedure exists because no AWS resources are created by this repository.** When the Section-21
infrastructure is authored, it must ship its own destroy path (e.g. `terraform destroy` / `aws cloudformation
delete-stack`) plus a manual checklist for the EBS volume, the Elastic IP, the security group, the IAM instance
profile/role, the SSM parameters, and the CloudWatch log groups.

---

## 38. Non-Negotiable Final Questions — answered

1. **Can an anonymous internet user execute arbitrary code on the CRYPTIQ server through a malicious repository?**
   **No.** Tested with `setup.py`/`conftest.py`/`Makefile`/`os.system`/`exec(compile())` side-effect markers through the
   exact worker path (`analyze_snapshot`) with socket + subprocess tripwires: no marker written, no socket, no process.
   The engine is `ast.parse` + AST walk; it imports nothing from the target tree; no `eval`/`exec`/`subprocess`/
   `importlib` anywhere in `app/engine/`.

2. **Can a malicious repository reach AWS metadata or private network resources?**
   **No.** Repo URL must be `https://github.com/{owner}/{name}` (24-payload probe rejected localhost, `169.254.169.254`,
   decimal/hex/IPv6 literals, credential and port tricks). Every actual request is built from a validated owner/name/SHA
   and checked against a 4-host allow-list; IP literals are refused; every redirect hop is re-validated; a
   resolves-to-public DNS check runs on top. (There is no AWS deployment, so there is also no metadata endpoint to
   reach.)

3. **Can a malicious repository escape its extraction directory?**
   **No.** 15-case hostile-archive battery: `../`, nested `../`, absolute, Windows drive, backslash, escaping symlink,
   absolute symlink, device member, oversize, bomb, malformed — all rejected or safely skipped; no filesystem artifact
   outside the temp root in any case. Extraction target is re-checked with `resolve()` against the destination root.

4. **Can repository code execute?**
   **No** — server (Q1) and CLI local mode (`git archive` runs no hook; only read-only `git` subcommands via argv, no
   shell; `tests/security/test_cli_security.py` confirms markers never fire).

5. **Can repository content inject instructions into Gemini and alter deterministic results?**
   **No.** The excerpt is a bounded, schema-typed field flagged as untrusted data in the system instruction; more
   fundamentally, the explanation response DTO contains only prose fields, so algorithm/role/confidence/PQC/priority are
   structurally incapable of being changed by any model output. Malformed output → schema-validation failure → 503, no
   change.

6. **Can a user obtain Gemini/GitHub/AWS credentials?**
   **No.** No real secret in git history, `.env` (blank), image layers, running container env, the built frontend
   bundle, error bodies, or logs (only exception *types* are logged for outbound failures; the API key is never logged).
   Secrets are backend-env only. (No AWS credentials exist in the project.)

7. **Can one scan corrupt another scan?**
   **No** observed path. Each scan is its own `Scan` + `ScanJob` row; the worker uses a per-job session and one
   persist transaction; the evidence-required flush invariant prevents bare findings. The concurrency defect that
   existed (D-1) produced clean 500s + rollbacks, never cross-scan corruption, and is now fixed.

8. **Can failed scans become cache hits?**
   **No.** `find_completed_scan` matches `Scan.status == COMPLETED` only; the worker's `_fail` path sets `FAILED` and
   persists no findings; verified live (a scan of a non-existent commit went `FAILED` and was not reused).

9. **Does the CLI produce the same deterministic fingerprints as the API?**
   **Yes.** `latchset/jwcrypto@48f1e80` gave 52 findings via CLI-local **and** via the Docker API/worker; `cryptiq diff`
   keeps a finding's fingerprint stable across a pure line-number shift (RSA finding moved line 2→5, still `UNCHANGED`).

10. **Does CRYPTIQ work on repositories other than pyca/cryptography?**
    **Yes.** `pallets/click` (0, correct), `latchset/jwcrypto` (52, third-party consumer of the library), plus 5
    synthetic repos and a 1 200-file scale test — no crashes, correct localisation, bounded memory.

11. **Does it handle repositories with zero cryptographic findings?**
    **Yes.** `pallets/click` and synthetic repo E (including `hashlib.md5`, deliberately out of the `cryptography`-
    library scope) → 0 findings, exit 0, no error.

12. **Can the AWS deployment be rebuilt from scratch?**
    **No — there is nothing to rebuild.** No IaC, user-data, or deployment scripts exist. The *container* layer rebuilds
    cleanly (`docker compose build && up -d`, entrypoint runs migrations, healthy in ~40 s).

13. **Can the operator diagnose failures from CloudWatch?**
    **Not as shipped** — logs go to stdout/stderr (correct for containers) but no CloudWatch agent/config exists. Locally
    `docker compose logs` shows queued/started/completed/failed + Gemini/GitHub failures with no secrets.

14. **Can the entire AWS environment be destroyed cleanly?**
    **N/A** — no AWS environment is created by this repo, so there is nothing to destroy and no teardown procedure. This
    must be authored alongside the infrastructure.

15. **Is anything currently a hard blocker for the hackathon?**
    **For a local / single-VM Docker-Compose demo: no** (D-1 fixed; all bare-minimum security controls verified).
    **For the specific AWS endpoint in Section 21: yes** — the entire AWS deployment layer (provisioning, host proxy on
    :80, IAM, SSM secrets, CloudWatch shipping, security group, teardown) is absent and must be built and then
    exposure-tested from an external network before judges are pointed at a public IP.

---

## Evidence appendix — test / input / expected / actual / result (selected)

| # | Test | Input | Expected | Actual | Result |
|---|---|---|---|---|---|
| E1 | Engine never-executes | hostile repo (markers) → `analyze_snapshot` + socket/subprocess tripwires | no side effect | `/tmp/CRYPTIQ_ENGINE_PWNED` absent; 3 correct findings (RSA keygen, RSA sign, ECDH) | PASS |
| E2 | SSRF repo-URL parse | 24 payloads | reject all non-github.com | 24/24 rejected; only canonical accepted | PASS |
| E3 | SSRF outbound guard | metadata IP / loopback / IPv6 / decimal IP / suffix tricks | refuse | refused; 4-host allow-list only | PASS |
| E4 | Hostile archives | 15 payloads | reject/skip, no escape | 15/15 safe; no FS artifact outside root | PASS |
| E5 | API fuzz | 19 malformed requests | 4xx, stable schema, no leak | 422/404/405 as appropriate; `{"error":{"code","message"}}`; no traceback/path/SQL | PASS |
| E6 | Concurrency (pre-fix) | 15× identical `POST /scans`, new repo | all 202 | 11×202, 4×500 (`UNIQUE constraint`) | FAIL → fixed |
| E7 | Concurrency (post-fix) | same | all 202 | 15×202 | PASS |
| E8 | SQLite contention | 200 reads during a real worker persist | no lock error | 0 errors; scan COMPLETED, 52 findings | PASS |
| E9 | Determinism | scan repo F ×3 | identical | identical fingerprints + body + priority `[110,110,110,95,110,110,65,65,65,65,65]` | PASS |
| E10 | Adversarial parser precision | repo G | exactly the 3 real calls | exactly 3; docstring/string/comment/var/annotation/`getattr` ignored | PASS |
| E11 | Role epistemics | bare `rsa.generate_private_key` | role UNKNOWN, not a migration candidate | role `UNKNOWN`, `candidate:false`, "A reviewer must establish the review path." | PASS |
| E12 | PQC language | ECDSA sign | "Review against …" not "Replace with …" | "Review against the FIPS 204 (ML-DSA) and FIPS 205 (SLH-DSA) …" | PASS |
| E13 | Multi-repo | click / jwcrypto / cryptography | 0 / >0 localised / many, no crash | 0 / 52 in jwa.py+jwk.py / 1054, no crash | PASS |
| E14 | PyCryptodome | `Crypto.*` fixture | (scope-dependent) | 0 findings — unsupported, safe | YELLOW |
| E15 | CLI diff | line-shift + add + remove | UNCHANGED / NEW / FIXED | 1 UNCHANGED (line 2→5), 1 NEW, 1 FIXED; deterministic | PASS |
| E16 | CLI offline | `env -i` local scan | works with no network/DB/API/Gemini | 11 findings | PASS |
| E17 | Gemini no-key | explanation request | 503 `AI_EXPLANATION_UNAVAILABLE`, finding intact | as expected | PASS |
| E18 | Docker runtime | `docker inspect` live | non-root, no priv, no socket, no secret | all confirmed (uid 1001 / uid 101) | PASS |
| E19 | E2E via compose | submit through nginx → worker → findings → restart → cache | COMPLETED, persists, cache hit | 52 findings; survived `restart backend`; resubmit `cached:true` | PASS |
| E20 | Full regression | `pytest -q`; `ruff check`; frontend `tsc`/`eslint`/`vitest`/`build` | green | 811 pass / 34 skip; ruff clean; FE 57 pass + typecheck + lint + build | PASS |
| E21 | AWS deployment artifacts | search repo for EC2/CloudWatch/SSM/IaC/teardown | present | **absent** (repo docs confirm "NOT IMPLEMENTED") | RED |
| E22 | Trivy image scan | run locally | — | Trivy not installed | NOT TESTED (CI gate exists) |
| E23 | AWS exposure test | external hit on public IP | — | no infra, no creds, not authorised | NOT TESTED |
| E24 | Gemini live call | real API | — | no `GEMINI_API_KEY` | NOT TESTED (no-key path IS tested) |
```
