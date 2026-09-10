# Cryptiq CLI

`cryptiq` is the standalone command-line interface to the Cryptiq
deterministic cryptographic analysis engine. It runs in two modes over **one**
engine:

```
LOCAL                              REMOTE
  cryptiq CLI                        cryptiq CLI
      |                                  |  HTTP
  Analysis Engine                    Cryptiq FastAPI
      |                                  |
  local Git repo / source tree       Analysis Engine
```

The engine — parsing, rules, role inference, PQC mapping, impact analysis,
priority scoring, fingerprints, evidence — is the same code in both modes
(`app/engine/`). The CLI adds no analysis of its own.

---

## Installation

The CLI ships with the backend package. Install it as a normal Python command:

```bash
pip install -e ".[dev]"     # from cryptiq/, exposes the `cryptiq` console script
# or, without installing:
python -m app.cli --help
```

Verify:

```bash
cryptiq            # bare command -> the help screen, exit 0
cryptiq --help
cryptiq --version  # just the CLI version
cryptiq version    # CLI version + engine stamps
```

`cryptiq version` prints the CLI version and the engine version stamps
(`parser_version`, `ruleset_version`, `pqc_ruleset_version`) that make a scan
reproducible. `cryptiq --version` prints only the short `cryptiq <x.y.z>` line.
Running `cryptiq` with no arguments prints this help and exits `0` — it never
starts a server, opens a browser or runs a scan.

---

## Commands

| Command | Mode | Purpose |
| --- | --- | --- |
| `cryptiq scan <target>` | local / remote | Analyse a repository |
| `cryptiq diff --base <sha> --head <sha>` | local | Fingerprint diff of two commits |
| `cryptiq finding <finding_id>` | remote | One finding, full detail |
| `cryptiq review-queue` | remote | The global review queue |
| `cryptiq review-update <review_id>` | remote | Move a review item |
| `cryptiq scan-status <scan_id>` | remote | Poll a remote scan |
| `cryptiq findings <scan_id>` | remote | List a remote scan's findings |
| `cryptiq demo` | remote | Run the acceptance scan end to end |
| `cryptiq version` | — | CLI + engine versions |

`finding`, `review-queue`, `review-update`, `findings`, `scan-status` and
`demo` operate on the persistent scan/review store, which only the API owns, so
they are remote-only. They never fabricate rows when the API is unavailable —
they report the connection error and exit non-zero.

Help is available everywhere: `cryptiq --help`, `cryptiq scan --help`,
`cryptiq diff --help`, …

---

## Local scanning

```bash
cryptiq scan .                       # current directory (working tree)
cryptiq scan /path/to/repository     # absolute path
cryptiq scan ../other-project        # relative path
```

The target may be any directory. If it is a Git working tree, the current
working-tree state is analysed in place and the HEAD SHA is recorded for
reference. If it is not a Git repository, the directory is analysed directly.

Local scanning is **completely offline**. It never starts, needs or contacts
FastAPI, PostgreSQL, SQLite, Docker, Redis, Celery, Kafka, a cloud service or
Gemini, and the source never leaves the machine.

### Vendored directories

A working-tree scan skips common dependency / virtualenv / cache directories by
default (`.git`, `node_modules`, `.venv`, `venv`, `site-packages`,
`__pycache__`, `.tox`, `.mypy_cache`, `.pytest_cache`, `.ruff_cache`, …). Pass
`--include-all` for exact parity with the engine's own discovery (slower, and
it will read vendored code).

A `--commit` scan never needs this: `git archive` only ever contains tracked
files.

### Context-Aware Scanning (`--domain`)

Supply an application domain profile to produce context-aware migration assessments alongside deterministic findings:

```bash
cryptiq scan . --domain autonomous-drone
cryptiq scan . --domain cloud-infrastructure
cryptiq scan . --domain fintech
cryptiq scan . --domain healthcare
cryptiq scan . --domain general-software
```

Available presets configure latency sensitivity, bandwidth limits, memory, compute, battery, and platform constraints. When combined with `--format json` or `--format sarif`, the output includes the full `contextual_assessment` or `contextualAssessment` property.

---

## Git commits

```bash
cryptiq scan . --commit 1f903f5ed2e5e316f345a927555e48535829d8de
cryptiq scan /path/to/repo --commit v3.2          # any rev git can resolve
cryptiq scan . --commit 1f903f5                   # short SHA, resolved locally
```

When a commit is supplied:

* the revision is resolved **locally** with `git rev-parse` — nothing is
  fetched; the commit must already exist in the local object store;
* the tree is read with `git archive <sha>` into a private temporary
  directory. The working tree and the current branch are never checked out,
  reset or modified, and uncommitted changes are untouched;
* the archive extractor writes **regular files only** — symlinks, hardlinks
  and device entries are skipped, never recreated — so nothing in the archive
  can point outside the snapshot root;
* no repository code, build system, test suite or package install is ever run.
  The only process the CLI spawns is `git` itself, read-only.

---

## Remote scanning

Remote mode is a thin HTTP client of a running Cryptiq API. It contains no
analysis logic:

```
cryptiq CLI ── HTTP ──▶ FastAPI ──▶ ScanService ──▶ AnalysisEngine
```

```bash
# submit only (prints the scan id) — the shape CI has always used
cryptiq scan https://github.com/org/repo --remote --commit <sha>

# submit, poll to completion, then print the findings
cryptiq scan https://github.com/org/repo --remote --commit <sha> --wait

# same, as JSON or SARIF
cryptiq scan https://github.com/org/repo --remote --commit <sha> --format sarif
```

A target that starts with `http://` or `https://` selects remote mode
automatically; `--remote` forces it.

The API base URL comes from `--api-url`, then `$CRYPTIQ_API_URL`, then
`http://localhost:8000/api/v1`. It is never hardcoded.

---

## Common result model

Local and remote results are normalised into one representation
(`app.cli.results.CliFinding`) before rendering, so a result reads the same
regardless of where it came from. Every finding preserves the deterministic
blocks:

```
OBSERVED    rule, algorithm, api, primitive, library, operation, file, lines, evidence
INFERENCE   role, confidence, basis, rationale
MIGRATION   PQC family, candidate, current, standards / migration notes
IMPACT      scope, nodes, relationships (bounded, statically observed)
PRIORITY    HIGH / MEDIUM / LOW, deterministic score, deterministic reasons
REVIEW      lifecycle state + metadata (remote only; N/A locally)
```

A value the engine or API did not provide is rendered `N/A` and serialised as
`null`. The CLI never invents a missing deterministic field.

---

## Finding inspection

```bash
cryptiq finding <finding_id>              # API detail view
cryptiq finding <finding_id> --grouped    # OBSERVED / INFERENCE / ... layout
cryptiq finding <finding_id> --json
```

AI explanation is never requested automatically by any command, in any mode.

---

## Review queue

```bash
cryptiq review-queue
cryptiq review-queue --priority high --status open
cryptiq review-queue --json               # machine-readable
```

Columns: finding id, repository, file, algorithm, role, migration review path,
priority, review state.

---

## Diff mode

```bash
cryptiq diff --base <sha> --head <sha>                 # target defaults to .
cryptiq diff --target /path/to/repo --base v1 --head v2
cryptiq diff --base <sha> --head <sha> --json
```

Both commits are analysed by the deterministic engine, then findings are
compared **by CRYPTIQ fingerprint** — never by line number. The fingerprint
excludes line numbers, columns and the commit SHA, so inserting a line above a
call keeps its finding `UNCHANGED`.

Output is three ordered buckets:

```
CRYPTIQ DIFF
Repository: org/repo
Base:       <sha>
Head:       <sha>

NEW (2)
  HIGH     RSA        src/foo.py:42
  HIGH     ECDSA      src/bar.py:91
FIXED (1)
  MEDIUM   SHA-1      src/old.py:17
UNCHANGED (37)
  ...
```

The diff is deterministic and never calls Gemini.

---

## Output formats

| Flag | Commands | Result |
| --- | --- | --- |
| *(none)* | all | Human-readable tables / blocks |
| `--json` | all | Machine-readable JSON on stdout |
| `--format sarif` / `--sarif` | `scan` | Valid **SARIF 2.1.0** (`--sarif` is shorthand) |

SARIF conventions match the CI self-scan converter
(`.github/scripts/findings_to_sarif.py`):

* one rule per `algorithm` + `operation`, id `cryptiq/<slug>`, rules sorted;
* level: `high`/`critical` → `error`, `medium` → `warning`,
  `low`/`informational` → `note`;
* `artifactLocation.uri` is repository-relative — an absolute local path is
  never emitted;
* `partialFingerprints` carries `cryptiqFingerprint/v1` (the stable engine
  fingerprint), `cryptiqFindingId/v1` and `cryptiqFindingKey/v1` so GitHub
  code scanning can track a finding across commits.

SARIF output is byte-identical for the same repository state.

---

## Exit codes

| Code | Meaning |
| --- | --- |
| `0` | Success / no blocking findings |
| `1` | Completed, but findings need attention — `scan` found a finding at or above `--fail-on` (default `high`); `diff` found NEW findings; also a generic remote-request failure (unreachable API, rejected request) |
| `2` | Invalid usage or arguments (bad path, unresolved commit, `--commit` on a non-Git directory, unknown flag) |
| `3` | Operational error — Git failure, filesystem limit exceeded, a remote scan that reached `FAILED` |
| `4` | A requested remote resource was not found (`finding` / `scan-status` on an unknown id) |

`scan` exit behaviour is controlled by `--fail-on {never,low,medium,high}`
(default `high`). `--fail-on never` always exits `0` on a successful scan.
`diff` exits `1` on any NEW finding unless `--no-fail-on-new` is given.

Exit codes never depend on the formatted terminal output, so CI can rely on
them with `--json` or `--format sarif`.

---

## Environment variables

| Variable | Used by | Effect |
| --- | --- | --- |
| `CRYPTIQ_API_URL` | remote commands | API base URL (default `http://localhost:8000/api/v1`) |
| `CRYPTIQ_MAX_FILES` / `MAX_FILES` | local scan | File-count ceiling (settings) |
| `CRYPTIQ_MAX_FILE_BYTES` / `MAX_FILE_BYTES` | local scan | Per-file size ceiling |
| `GITHUB_TOKEN` | backend only | Not read by the CLI; never printed |
| `GEMINI_API_KEY` | backend only | Not read by the CLI; never printed |

The CLI never prints GitHub tokens, Gemini keys or database credentials, and
never logs secrets.

---

## CI usage

Every command is non-interactive: no prompts, no browser auth, no stdin.

```yaml
# Local self-scan → SARIF → GitHub code scanning
- run: cryptiq scan . --format sarif > cryptiq.sarif
- run: test "$(jq -r .version cryptiq.sarif)" = "2.1.0"
- uses: github/codeql-action/upload-sarif@v3
  with: { sarif_file: cryptiq.sarif }

# Gate a PR on new findings vs. the base branch
- run: cryptiq diff --base "origin/${{ github.base_ref }}" --head HEAD
```

`--json` / `--format sarif` write machine-readable output to **stdout**;
diagnostics and errors go to **stderr**. The existing API-backed self-scan job
(`python -m app.cli scan <url> <sha> --json` + `scan-status`) is unchanged.

---

## Docker

The CLI is part of the backend image, so it is available wherever the backend
runs:

```bash
docker compose exec backend cryptiq --help
docker compose exec backend cryptiq version
docker compose exec backend cryptiq review-queue --json
```

---

## Security model

The CLI is a static-analysis tool and behaves like one:

* **never executes target repository code** — no `setup.py`, `conftest.py`,
  build system, test suite or package install is run; the only subprocess is
  read-only `git`;
* **never imports target Python modules** — files are read as text and parsed
  with the `ast` module;
* **path traversal is refused** — archive members and snapshot reads that
  escape the root are rejected;
* **symlinks are not followed** — in the tree walk, in the working-tree scan,
  and in `git archive` extraction;
* **resource limits are enforced** — the ingestion file-count and file-size
  ceilings from settings apply to local trees; an oversized repository is
  rejected, not partially analysed;
* **offline** — local mode makes no network connection;
* **no secret leakage** — tokens and keys are never read, printed or logged.

---

## Examples

```bash
cryptiq scan .
cryptiq scan . --json
cryptiq scan . --format sarif
cryptiq scan . --commit 1f903f5ed2e5e316f345a927555e48535829d8de
cryptiq scan /path/to/repo --commit v3.2 --fail-on medium
cryptiq finding 7f113028-8580-404a-ad98-ae48fed3fb2f --grouped
cryptiq review-queue --json
cryptiq diff --base 6e6f333 --head 148cb06
cryptiq scan https://github.com/org/repo --remote --commit <sha>
cryptiq scan https://github.com/org/repo --remote --commit <sha> --wait --format sarif
cryptiq version --json
```
