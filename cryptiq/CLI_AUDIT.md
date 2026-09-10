
---

## Addendum — standalone CLI (local + remote over one engine)

The CLI is no longer HTTP-only. It now runs in two modes over the **same**
`app.engine` pipeline; there is still exactly one analysis implementation.

### Audit of what already existed

* `app/cli/` — argparse CLI, HTTP-only (`client.py`, `main.py`, `render.py`).
  25 tests in `tests/unit/test_cli.py`. Console script `cryptiq =
  app.cli.main:main` in `pyproject.toml`.
* Engine entry point reused unchanged: `app.engine.pipeline.analyze_snapshot(
  ingestion, root)` → `AnalysisResult(findings=tuple[AnalyzedFinding])`, the
  exact call `app/worker.py` makes.
* `IngestionResult` / `SourceSnapshot` / `discover_files` / `IngestionLimits`
  reused to feed the pipeline without the GitHub provider.
* Fingerprints: `app.engine.fingerprints.finding_fingerprint` (line-independent)
  reused for the diff — no new identity scheme.
* SARIF: conventions copied from `.github/scripts/findings_to_sarif.py`.

Nothing in parsing, rules, roles, PQC mapping, impact, priority, fingerprints,
finding models or evidence was duplicated or reimplemented.

### New CLI modules

| File | Role |
| --- | --- |
| `app/cli/local.py` | Build a `SourceSnapshot` from a local dir or `git archive <sha>`; run `analyze_snapshot`. No network, no DB. |
| `app/cli/results.py` | `CliFinding` — one representation for local `AnalyzedFinding` and remote `ApiFindingDto`. |
| `app/cli/sarif.py` | SARIF 2.1.0 emitter, same conventions as the CI converter. |
| `app/cli/diff.py` | Analyse two commits, compare by fingerprint → NEW / FIXED / UNCHANGED. |

`app/cli/main.py` gained `scan` (local default, `--remote` for the API),
`diff`, `version`; `render.py` gained the grouped/`CliFinding` renderers. The
one additive backend change: `ApiFindingDto.fingerprint` is now populated
(optional field) so remote SARIF carries the real engine fingerprint.

### Commands

`scan <target> [commit]`, `diff --base --head`, `version`, plus the unchanged
remote commands `scan-status`, `findings`, `finding`, `review-queue`,
`review-update`, `demo`.

### Exit codes

`0` ok / no blocking findings · `1` findings need attention (`scan` over
`--fail-on`, `diff` NEW) or generic remote failure · `2` usage · `3`
operational (git/fs/API/FAILED) · `4` remote resource not found. Never depends
on formatted output.

### Validation

* `pyca/cryptography @ 1f903f5…`: local `cryptiq scan --commit` produces
  **1042 findings / 136 HIGH / 906 MEDIUM / 241 files** — identical to the
  backend's stored acceptance scan, and the **1042 fingerprints match the API
  set exactly** (0 local-only, 0 remote-only).
* Repeated local scans are byte-identical.
* New tests: `tests/unit/test_cli_local.py`, `test_cli_diff.py`,
  `test_cli_results.py`, `test_cli_sarif.py`, `test_cli_remote.py`,
  `tests/security/test_cli_security.py`. Full suite 809 passed / 34 skipped,
  ruff clean.
