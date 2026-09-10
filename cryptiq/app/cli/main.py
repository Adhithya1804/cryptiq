"""``cryptiq`` command-line interface.

One CLI, two execution modes over **one** analysis engine:

* **local** -- ``cryptiq scan <path>`` runs
  :func:`app.engine.pipeline.analyze_snapshot` in-process over a local
  directory or Git commit. No FastAPI, database, Docker, Redis, Celery, Kafka,
  cloud service or Gemini is involved, and the source never leaves the
  machine.
* **remote** -- ``cryptiq scan <url> --remote`` (and ``scan-status`` /
  ``findings`` / ``finding`` / ``review-queue`` / ``review-update`` / ``demo``)
  is a thin HTTP client of the running FastAPI backend, which runs the same
  engine behind ``ScanService``.

Commands
--------
* ``cryptiq scan <target> [commit]``   -- analyse a repo (local by default)
* ``cryptiq diff --base <sha> --head <sha>`` -- fingerprint diff of two commits
* ``cryptiq finding <finding_id>``     -- one finding, full detail (remote)
* ``cryptiq review-queue``             -- the global review queue (remote)
* ``cryptiq version``                  -- CLI + engine version stamps
* ``cryptiq scan-status`` / ``findings`` / ``review-update`` / ``demo`` -- remote

Exit codes
----------
* 0  success / no blocking findings
* 1  completed, but findings need attention (``scan`` over ``--fail-on``;
     ``diff`` with NEW findings); also a generic remote-request failure
     (an unreachable API, a rejected request)
* 2  invalid usage or arguments
* 3  operational error -- Git, filesystem, or a FAILED remote scan
* 4  a requested remote resource was not found
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections.abc import Callable, Sequence
from typing import Any

from app import __version__ as CRYPTIQ_VERSION
from app.cli.client import (
    EXIT_FAILURE,
    EXIT_OK,
    EXIT_SCAN_FAILED,
    EXIT_USAGE,
    CliError,
    CryptiqClient,
)
from app.cli.diff import run_diff
from app.cli.local import local_analysis
from app.cli.render import (
    render_cli_finding,
    render_diff,
    render_finding_detail,
    render_local_summary,
    render_table,
    value_or_na,
)
from app.cli.results import PRIORITY_RANK, CliFinding
from app.cli.sarif import build_sarif
from app.engine import engine_versions

#: Same alias-friendly meaning as the task's table: exit 1 == "attention".
EXIT_FINDINGS = EXIT_FAILURE

DEMO_REPOSITORY = "https://github.com/pyca/cryptography"
DEMO_COMMIT = "1f903f5ed2e5e316f345a927555e48535829d8de"

PRIORITY_CHOICES = ["critical", "high", "medium", "low", "informational"]
ROLE_CHOICES = [
    "digital_signature",
    "key_establishment",
    "symmetric_encryption",
    "hash",
    "protocol",
    "unknown",
]
REVIEW_STATUS_CHOICES = [
    "open",
    "in_review",
    "resolved",
    "accepted_risk",
    "false_positive",
]
CONFIDENCE_CHOICES = ["high", "medium", "low"]
FAIL_ON_CHOICES = ["never", "low", "medium", "high"]

_ACTIVE_SCAN_STATES = {"QUEUED", "RUNNING"}
_REMOTE_PREFIXES = ("http://", "https://")


# --------------------------------------------------------------------------- #
# output helpers
# --------------------------------------------------------------------------- #


def _print_json(data: Any) -> None:
    print(json.dumps(data, indent=2, sort_keys=True))


def _emit(data: Any, *, as_json: bool, text: str) -> None:
    if as_json:
        _print_json(data)
    else:
        print(text)


def _repo_label(repository: dict[str, Any] | None) -> str:
    if not repository:
        return value_or_na(None)
    owner = repository.get("owner")
    name = repository.get("name")
    if owner and name:
        return f"{owner}/{name}"
    return value_or_na(repository.get("url"))


def _fail_on_threshold(token: str) -> int:
    """Return the priority rank at or above which ``scan`` should exit 1."""
    if token == "never":
        return 999
    return PRIORITY_RANK[token.upper()]


def _dedupe(findings: list[CliFinding]) -> list[CliFinding]:
    """One finding per fingerprint, first in engine order (matches persistence)."""
    seen: set[str] = set()
    kept: list[CliFinding] = []
    for finding in findings:
        key = finding.fingerprint or ""
        if key and key in seen:
            continue
        if key:
            seen.add(key)
        kept.append(finding)
    return kept


def _scan_output_format(args: argparse.Namespace) -> str:
    if getattr(args, "sarif", False):
        return "sarif"
    if getattr(args, "json", False):
        return "json"
    return getattr(args, "format", "text") or "text"


# --------------------------------------------------------------------------- #
# scan -- local or remote
# --------------------------------------------------------------------------- #


def _is_remote_target(target: str, remote_flag: bool) -> bool:
    return remote_flag or target.lower().startswith(_REMOTE_PREFIXES)


def cmd_scan(client_factory: Callable[[str | None], CryptiqClient], args: argparse.Namespace) -> int:
    commit = args.commit or args.commit_arg
    if _is_remote_target(args.target, args.remote):
        return _scan_remote(client_factory, args, commit)
    if args.commit_arg and not args.commit:
        # `scan <path> <sha>` -- second positional is the commit in local mode.
        commit = args.commit_arg
    return _scan_local(args, commit)


def _scan_local(args: argparse.Namespace, commit: str | None) -> int:
    fmt = _scan_output_format(args)
    with local_analysis(
        args.target, commit=commit, include_all=args.include_all
    ) as (result, meta):
        findings = _dedupe([CliFinding.from_analyzed(f) for f in result.findings])
        findings.sort(key=lambda f: f.sort_key)

        if fmt == "sarif":
            automation = f"cryptiq/local/{meta.commit_sha}" if meta.commit_sha else "cryptiq/local"
            print(
                json.dumps(
                    build_sarif(
                        findings, automation_id=automation, tool_version=CRYPTIQ_VERSION
                    ),
                    indent=2,
                )
            )
        elif fmt == "json":
            _print_json(
                {
                    "target": meta.target,
                    "repository": meta.repository_label,
                    "mode": meta.mode,
                    "commit_sha": meta.commit_sha,
                    "dirty": meta.dirty,
                    "files_analyzed": result.analyzed_files,
                    "files_discovered": result.total_files,
                    "engine": _engine_dict(),
                    "findings": [f.to_dict() for f in findings],
                    "summary": _summary_counts(findings),
                }
            )
        else:
            print(
                render_local_summary(
                    meta,
                    findings,
                    files_analyzed=result.analyzed_files,
                    total_files=result.total_files,
                )
            )

    threshold = _fail_on_threshold(args.fail_on)
    if any(f.priority_rank >= threshold for f in findings):
        return EXIT_FINDINGS
    return EXIT_OK


def _scan_remote(
    client_factory: Callable[[str | None], CryptiqClient],
    args: argparse.Namespace,
    commit: str | None,
) -> int:
    if not commit:
        raise CliError(
            "Remote scan needs a commit: pass it as the second argument or with --commit.",
            exit_code=EXIT_USAGE,
        )
    fmt = _scan_output_format(args)
    wants_findings = args.wait or fmt == "sarif"

    with client_factory(args.api_url) as client:
        inspection, cached = client.create_scan(args.target, commit)
        scan_id = inspection["id"]

        if not wants_findings:
            if fmt == "json":
                _print_json(inspection)
            else:
                lines = [
                    "Cryptiq Scan",
                    f"Repository: {_repo_label(inspection.get('repository'))}",
                    f"Commit: {value_or_na(inspection.get('commit_sha'))}",
                ]
                if cached:
                    lines.append("Status: CACHED")
                    lines.append(f"Scan ID: {value_or_na(scan_id)}")
                    lines.append("Existing result reused.")
                else:
                    lines.append(
                        f"Status: {value_or_na(inspection.get('status')) or 'QUEUED'}"
                    )
                    lines.append(f"Scan ID: {value_or_na(scan_id)}")
                print("\n".join(lines))
            return EXIT_OK

        inspection = _poll_remote_scan(client, scan_id, inspection, args)
        if inspection.get("status") == "FAILED":
            raise CliError(
                f"Remote scan {scan_id} FAILED: {value_or_na(inspection.get('error_code'))}",
                exit_code=EXIT_SCAN_FAILED,
            )
        findings = _fetch_all_remote_findings(client, scan_id)

    findings.sort(key=lambda f: f.sort_key)
    if fmt == "sarif":
        print(
            json.dumps(
                build_sarif(
                    findings,
                    automation_id=f"cryptiq/remote/{scan_id}",
                    tool_version=CRYPTIQ_VERSION,
                ),
                indent=2,
            )
        )
    elif fmt == "json":
        _print_json(
            {
                "scan_id": scan_id,
                "repository": _repo_label(inspection.get("repository")),
                "commit_sha": inspection.get("commit_sha"),
                "status": inspection.get("status"),
                "findings": [f.to_dict() for f in findings],
                "summary": _summary_counts(findings),
            }
        )
    else:
        print(f"CRYPTIQ SCAN (remote)  scan {scan_id}  status {inspection.get('status')}")
        print(f"Findings: {len(findings)}")
        print(_remote_findings_table(findings))

    threshold = _fail_on_threshold(args.fail_on)
    if any(f.priority_rank >= threshold for f in findings):
        return EXIT_FINDINGS
    return EXIT_OK


def _poll_remote_scan(
    client: CryptiqClient, scan_id: str, inspection: dict, args: argparse.Namespace
) -> dict:
    deadline = time.monotonic() + args.timeout
    status = inspection.get("status")
    while status in _ACTIVE_SCAN_STATES:
        if time.monotonic() > deadline:
            raise CliError(
                f"Remote scan {scan_id} did not finish within {args.timeout}s "
                f"(last status: {status}).",
                exit_code=EXIT_SCAN_FAILED,
            )
        time.sleep(args.poll_interval)
        inspection = client.get_scan(scan_id)
        status = inspection.get("status")
    return inspection


def _fetch_all_remote_findings(client: CryptiqClient, scan_id: str) -> list[CliFinding]:
    """Page through the scan's findings and resolve each to full detail."""
    out: list[CliFinding] = []
    page = 1
    while True:
        envelope = client.list_findings(scan_id, page=page, page_size=200)
        items = envelope.get("items", [])
        for item in items:
            detail = client.get_finding(item["id"])
            out.append(CliFinding.from_finding_dto(detail))
        if page >= int(envelope.get("pages", 1)) or not items:
            break
        page += 1
    return out


def _remote_findings_table(findings: Sequence[CliFinding]) -> str:
    headers = ["PRIORITY", "SCORE", "ALGORITHM", "OPERATION", "ROLE", "FILE", "LINE"]
    rows = [
        [
            value_or_na(f.priority_level),
            value_or_na(f.priority_score),
            value_or_na(f.algorithm),
            value_or_na(f.operation),
            value_or_na(f.role),
            value_or_na(f.file_path),
            value_or_na(f.start_line),
        ]
        for f in findings
    ]
    return render_table(headers, rows, max_widths=[13, 6, 12, 16, 20, 44, 6])


def _summary_counts(findings: Sequence[CliFinding]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for finding in findings:
        key = (finding.priority_level or "UNKNOWN").upper()
        counts[key] = counts.get(key, 0) + 1
    counts["TOTAL"] = len(findings)
    return counts


def _engine_dict() -> dict[str, str]:
    versions = engine_versions()
    return {
        "parser_version": versions.parser_version,
        "ruleset_version": versions.ruleset_version,
        "pqc_ruleset_version": versions.pqc_ruleset_version,
    }


# --------------------------------------------------------------------------- #
# diff
# --------------------------------------------------------------------------- #


def cmd_diff(_client_factory: Any, args: argparse.Namespace) -> int:
    with run_diff(
        args.target, base=args.base, head=args.head, include_all=args.include_all
    ) as diff:
        if args.json or args.format == "json":
            _print_json(
                {
                    "repository": diff.repository_label,
                    "base_sha": diff.base_sha,
                    "head_sha": diff.head_sha,
                    "new": [f.to_dict() for f in diff.new],
                    "fixed": [f.to_dict() for f in diff.fixed],
                    "unchanged": [f.to_dict() for f in diff.unchanged],
                    "summary": {
                        "new": len(diff.new),
                        "fixed": len(diff.fixed),
                        "unchanged": len(diff.unchanged),
                    },
                }
            )
        else:
            print(render_diff(diff))
        has_new = diff.has_new
    if has_new and not args.no_fail_on_new:
        return EXIT_FINDINGS
    return EXIT_OK


# --------------------------------------------------------------------------- #
# version
# --------------------------------------------------------------------------- #


def cmd_version(_client_factory: Any, args: argparse.Namespace) -> int:
    eng = _engine_dict()
    if args.json:
        _print_json({"cryptiq": CRYPTIQ_VERSION, "engine": eng})
    else:
        print(f"cryptiq {CRYPTIQ_VERSION}")
        print(f"  parser_version      {eng['parser_version']}")
        print(f"  ruleset_version     {eng['ruleset_version']}")
        print(f"  pqc_ruleset_version {eng['pqc_ruleset_version']}")
    return EXIT_OK


# --------------------------------------------------------------------------- #
# remote-only commands (unchanged behaviour)
# --------------------------------------------------------------------------- #


def _scan_status_lines(inspection: dict[str, Any]) -> list[str]:
    severity = inspection.get("severity") or {}
    lines = [
        f"Scan ID:          {value_or_na(inspection.get('id'))}",
        f"Repository:       {_repo_label(inspection.get('repository'))}",
        f"Requested commit: {value_or_na(inspection.get('commit_sha'))}",
        f"Resolved commit:  {value_or_na(inspection.get('commit_sha'))}",
        f"Status:           {value_or_na(inspection.get('status'))}",
        f"Queued at:        {value_or_na(inspection.get('started_at'))}",
        f"Started at:       {value_or_na(inspection.get('started_at'))}",
        f"Completed at:     {value_or_na(inspection.get('completed_at'))}",
        f"Duration (ms):    {value_or_na(inspection.get('duration_ms'))}",
        f"Files analyzed:   {value_or_na(inspection.get('files_analyzed'))}",
        f"Findings:         {value_or_na(inspection.get('findings_count'))}",
    ]
    if severity:
        lines.append(
            "Severity:         "
            f"critical={severity.get('critical', 0)} high={severity.get('high', 0)} "
            f"medium={severity.get('medium', 0)} low={severity.get('low', 0)}"
        )
    if inspection.get("status") == "FAILED" or inspection.get("error_code"):
        lines.append(f"Error code:       {value_or_na(inspection.get('error_code'))}")
        lines.append(f"Error message:    {value_or_na(inspection.get('error_message'))}")
    return lines


def cmd_scan_status(client_factory: Callable[[str | None], CryptiqClient], args: argparse.Namespace) -> int:
    with client_factory(args.api_url) as client:
        inspection = client.get_scan(args.scan_id)
    _emit(inspection, as_json=args.json, text="\n".join(_scan_status_lines(inspection)))
    return EXIT_SCAN_FAILED if inspection.get("status") == "FAILED" else EXIT_OK


def _findings_table(items: list[dict[str, Any]]) -> str:
    headers = [
        "FINDING ID", "ALGORITHM", "OPERATION", "ROLE", "PRIORITY", "CONF",
        "FILE", "LINE", "REVIEW PATH",
    ]
    rows = [
        [
            item.get("id"), item.get("algorithm"), item.get("operation"),
            item.get("role"), item.get("priority"), item.get("confidence"),
            item.get("file_path"), item.get("start_line"), item.get("review_path"),
        ]
        for item in items
    ]
    widths = [36, 10, 16, 20, 13, 6, 34, 6, 26]
    return render_table(headers, rows, max_widths=widths)


def cmd_findings(client_factory: Callable[[str | None], CryptiqClient], args: argparse.Namespace) -> int:
    with client_factory(args.api_url) as client:
        page = client.list_findings(
            args.scan_id,
            page=args.page,
            page_size=args.page_size,
            priority=args.priority,
            algorithm=args.algorithm,
            role=args.role,
            status=args.status,
            confidence=args.confidence,
        )
    if args.json:
        _print_json(page)
        return EXIT_OK
    items = page.get("items", [])
    print(
        "\n".join(
            [
                _findings_table(items),
                "",
                f"Page {page.get('page', 1)} / {page.get('pages', 1)}",
                f"Total findings: {page.get('total', len(items))}",
            ]
        )
    )
    return EXIT_OK


def cmd_finding(client_factory: Callable[[str | None], CryptiqClient], args: argparse.Namespace) -> int:
    with client_factory(args.api_url) as client:
        finding = client.get_finding(args.finding_id)
    if args.json:
        _print_json(finding)
    elif args.grouped:
        print(render_cli_finding(CliFinding.from_finding_dto(finding)))
    else:
        print(render_finding_detail(finding))
    return EXIT_OK


def _queue_table(items: list[dict[str, Any]]) -> str:
    headers = [
        "REVIEW ID", "FINDING ID", "ALGORITHM", "ROLE", "PRIORITY", "STATUS",
        "FILE", "LINE",
    ]
    rows = [
        [
            item.get("review_id"), item.get("finding_id"), item.get("algorithm"),
            item.get("role"), item.get("priority"), item.get("status"),
            item.get("file_path"), item.get("start_line"),
        ]
        for item in items
    ]
    widths = [36, 36, 10, 20, 13, 16, 34, 6]
    return render_table(headers, rows, max_widths=widths)


def cmd_review_queue(client_factory: Callable[[str | None], CryptiqClient], args: argparse.Namespace) -> int:
    with client_factory(args.api_url) as client:
        envelope = client.review_queue(
            page=args.page,
            page_size=args.page_size,
            priority=args.priority,
            algorithm=args.algorithm,
            role=args.role,
            status=args.status,
        )
    if args.json:
        _print_json(envelope)
        return EXIT_OK
    items = envelope.get("items", [])
    print(
        "\n".join(
            [
                _queue_table(items),
                "",
                f"Review items: {envelope.get('total', len(items))}",
            ]
        )
    )
    return EXIT_OK


def cmd_review_update(client_factory: Callable[[str | None], CryptiqClient], args: argparse.Namespace) -> int:
    body: dict[str, Any] = {}
    if args.status is not None:
        body["status"] = args.status.upper()
    if args.assignee is not None:
        body["assigned_to"] = args.assignee or None
    if args.note is not None:
        body["note"] = args.note or None
    if not body:
        raise CliError(
            "Nothing to update: pass --status, --assignee or --note.",
            exit_code=EXIT_USAGE,
        )
    with client_factory(args.api_url) as client:
        review = client.update_review_item(args.review_id, body)
    text = "\n".join(
        [
            f"Review item: {value_or_na(review.get('id'))}",
            f"Status:      {value_or_na(review.get('status'))}",
            f"Assignee:    {value_or_na(review.get('assigned_to'))}",
            f"Note:        {value_or_na(review.get('note'))}",
            f"Updated:     {value_or_na(review.get('updated_at'))}",
        ]
    )
    _emit(review, as_json=args.json, text=text)
    return EXIT_OK


def cmd_demo(client_factory: Callable[[str | None], CryptiqClient], args: argparse.Namespace) -> int:
    out: dict[str, Any] = {"repository": DEMO_REPOSITORY, "commit": DEMO_COMMIT}
    if not args.json:
        print("Cryptiq demo")
        print(f"Repository: {DEMO_REPOSITORY}")
        print(f"Commit:     {DEMO_COMMIT}")

    with client_factory(args.api_url) as client:
        inspection, cached = client.create_scan(DEMO_REPOSITORY, DEMO_COMMIT)
        scan_id = inspection["id"]
        out["scan_id"] = scan_id
        out["cached"] = cached
        if not args.json:
            print(f"\n{'Cached result reused.' if cached else 'Queued.'} Scan ID: {scan_id}")

        deadline = time.monotonic() + args.timeout
        status = inspection.get("status")
        while status in _ACTIVE_SCAN_STATES:
            if time.monotonic() > deadline:
                raise CliError(
                    f"Scan {scan_id} did not finish within {args.timeout}s "
                    f"(last status: {status}).",
                    exit_code=EXIT_FAILURE,
                )
            time.sleep(args.poll_interval)
            inspection = client.get_scan(scan_id)
            status = inspection.get("status")
            if not args.json:
                print(f"  status: {status}")

        out["status"] = status
        out["findings_count"] = inspection.get("findings_count")
        if status == "FAILED":
            out["error_code"] = inspection.get("error_code")
            if args.json:
                _print_json(out)
            else:
                print(f"\nScan failed: {value_or_na(inspection.get('error_code'))}")
            return EXIT_SCAN_FAILED

        findings_page = client.list_findings(scan_id, page=1, page_size=args.sample_size)
        candidates_page = client.list_findings(
            scan_id, page=1, page_size=args.sample_size, priority="high"
        )
        queue = client.review_queue(page=1, page_size=1)

    out["sample_findings"] = findings_page.get("items", [])
    out["migration_candidates"] = [
        item
        for item in candidates_page.get("items", [])
        if item.get("is_migration_candidate")
    ]
    out["review_queue_total"] = queue.get("total")

    if args.json:
        _print_json(out)
        return EXIT_OK

    print(f"\nStatus: {status}")
    print(f"Findings: {value_or_na(inspection.get('findings_count'))}")
    print(f"\nSample findings (first {args.sample_size}):")
    print(_findings_table(findings_page.get("items", [])))
    print(f"\nMigration candidates (HIGH priority, first {args.sample_size}):")
    print(_findings_table(out["migration_candidates"]))
    print(f"\nReview queue items: {value_or_na(queue.get('total'))}")
    return EXIT_OK


# --------------------------------------------------------------------------- #
# argument parser
# --------------------------------------------------------------------------- #


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cryptiq",
        description="Cryptiq CLI -- deterministic post-quantum crypto analysis, "
        "local or against a Cryptiq API.",
    )
    parser.add_argument(
        "--api-url",
        default=None,
        help="Base URL of the Cryptiq API for remote commands "
        "(default: $CRYPTIQ_API_URL or http://localhost:8000/api/v1).",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"cryptiq {CRYPTIQ_VERSION}",
        help="Print the CLI version and exit.",
    )
    # Not required: a bare ``cryptiq`` prints the help screen and exits 0
    # (handled in ``main``), rather than erroring with exit 2.
    sub = parser.add_subparsers(dest="command", metavar="<command>")

    def _add_json(p: argparse.ArgumentParser) -> None:
        p.add_argument(
            "--json", action="store_true", help="Emit machine-readable JSON."
        )

    # -- scan ----------------------------------------------------------------
    p_scan = sub.add_parser(
        "scan",
        help="Analyse a repository. Local by default; --remote uses the API.",
        description=(
            "Local:  cryptiq scan .            cryptiq scan /path/to/repo "
            "--commit <sha>\n"
            "Remote: cryptiq scan https://github.com/org/repo --remote --commit <sha>"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p_scan.add_argument("target", help="A local path, or a repository URL with --remote.")
    p_scan.add_argument(
        "commit_arg",
        nargs="?",
        default=None,
        metavar="commit",
        help="Optional commit SHA (same as --commit; positional form kept for "
        "compatibility).",
    )
    p_scan.add_argument("-c", "--commit", default=None, help="Analyse this commit.")
    p_scan.add_argument("--remote", action="store_true", help="Use the Cryptiq API.")
    p_scan.add_argument(
        "--format",
        choices=["text", "json", "sarif"],
        default="text",
        help="Output format (default: text). SARIF is valid SARIF 2.1.0.",
    )
    p_scan.add_argument(
        "--sarif",
        action="store_true",
        help="Shorthand for --format sarif (valid SARIF 2.1.0 on stdout).",
    )
    p_scan.add_argument(
        "--fail-on",
        choices=FAIL_ON_CHOICES,
        default="high",
        dest="fail_on",
        help="Exit 1 when a finding at or above this priority is present "
        "(default: high). 'never' always exits 0 on success.",
    )
    p_scan.add_argument(
        "--include-all",
        action="store_true",
        help="Local working-tree scans: do not skip vendored/cache directories.",
    )
    p_scan.add_argument(
        "--wait",
        action="store_true",
        help="Remote: poll to completion and print the findings, not just the id.",
    )
    p_scan.add_argument("--poll-interval", type=float, default=2.0, dest="poll_interval")
    p_scan.add_argument("--timeout", type=float, default=600.0)
    _add_json(p_scan)
    p_scan.set_defaults(func=cmd_scan, needs_client=True)

    # -- diff --------------------------------------------------------------
    p_diff = sub.add_parser(
        "diff",
        help="Compare findings between two local commits by CRYPTIQ fingerprint.",
        description="cryptiq diff --base <sha> --head <sha> [--target <path>]",
    )
    p_diff.add_argument("--base", required=True, help="Base commit SHA / ref.")
    p_diff.add_argument("--head", required=True, help="Head commit SHA / ref.")
    p_diff.add_argument("--target", default=".", help="Local repository path (default: .).")
    p_diff.add_argument("--format", choices=["text", "json"], default="text")
    p_diff.add_argument("--include-all", action="store_true")
    p_diff.add_argument(
        "--no-fail-on-new",
        action="store_true",
        help="Exit 0 even when there are NEW findings.",
    )
    _add_json(p_diff)
    p_diff.set_defaults(func=cmd_diff, needs_client=False)

    # -- version ----------------------------------------------------------
    p_version = sub.add_parser("version", help="Print CLI and engine versions.")
    _add_json(p_version)
    p_version.set_defaults(func=cmd_version, needs_client=False)

    # -- remote: scan-status --------------------------------------------
    p_status = sub.add_parser("scan-status", help="Show a remote scan's status.")
    p_status.add_argument("scan_id")
    _add_json(p_status)
    p_status.set_defaults(func=cmd_scan_status, needs_client=True)

    # -- remote: findings ---------------------------------------------
    p_findings = sub.add_parser("findings", help="List a remote scan's findings.")
    p_findings.add_argument("scan_id")
    p_findings.add_argument("--page", type=int, default=1)
    p_findings.add_argument("--page-size", type=int, default=50, dest="page_size")
    p_findings.add_argument("--priority", choices=PRIORITY_CHOICES)
    p_findings.add_argument("--algorithm", help="Case-insensitive substring match.")
    p_findings.add_argument("--role", choices=ROLE_CHOICES)
    p_findings.add_argument("--status", choices=REVIEW_STATUS_CHOICES)
    p_findings.add_argument("--confidence", choices=CONFIDENCE_CHOICES)
    _add_json(p_findings)
    p_findings.set_defaults(func=cmd_findings, needs_client=True)

    # -- remote: finding --------------------------------------------
    p_finding = sub.add_parser("finding", help="Show one finding in full (remote).")
    p_finding.add_argument("finding_id")
    p_finding.add_argument(
        "--grouped",
        action="store_true",
        help="Use the OBSERVED/INFERENCE/... block layout.",
    )
    _add_json(p_finding)
    p_finding.set_defaults(func=cmd_finding, needs_client=True)

    # -- remote: review-queue ------------------------------------
    p_queue = sub.add_parser("review-queue", help="Show the global review queue (remote).")
    p_queue.add_argument("--page", type=int, default=None)
    p_queue.add_argument("--page-size", type=int, default=50, dest="page_size")
    p_queue.add_argument("--priority", choices=PRIORITY_CHOICES)
    p_queue.add_argument("--algorithm", help="Case-insensitive substring match.")
    p_queue.add_argument("--role", choices=ROLE_CHOICES)
    p_queue.add_argument("--status", choices=REVIEW_STATUS_CHOICES)
    _add_json(p_queue)
    p_queue.set_defaults(func=cmd_review_queue, needs_client=True)

    # -- remote: review-update ---------------------------------
    p_review = sub.add_parser(
        "review-update",
        help="Move one review item through a valid workflow transition (remote).",
    )
    p_review.add_argument("review_id")
    p_review.add_argument("--status", choices=REVIEW_STATUS_CHOICES)
    p_review.add_argument("--assignee", help="Set the assignee (empty string clears).")
    p_review.add_argument("--note", help="Set the note (empty string clears).")
    _add_json(p_review)
    p_review.set_defaults(func=cmd_review_update, needs_client=True)

    # -- remote: demo -----------------------------------------
    p_demo = sub.add_parser(
        "demo", help="Run the pyca/cryptography acceptance scan end to end (remote)."
    )
    p_demo.add_argument("--poll-interval", type=float, default=2.0, dest="poll_interval")
    p_demo.add_argument("--timeout", type=float, default=600.0)
    p_demo.add_argument("--sample-size", type=int, default=5, dest="sample_size")
    _add_json(p_demo)
    p_demo.set_defaults(func=cmd_demo, needs_client=True)

    return parser


def main(
    argv: list[str] | None = None,
    *,
    client_factory: Callable[[str | None], CryptiqClient] = CryptiqClient,
) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if getattr(args, "command", None) is None:
        # Bare ``cryptiq`` -- a useful landing screen, not a usage error.
        parser.print_help()
        return EXIT_OK

    try:
        return args.func(client_factory, args)
    except CliError as exc:
        print(f"error: {exc.message}", file=sys.stderr)
        return exc.exit_code
    except KeyboardInterrupt:  # pragma: no cover - interactive only
        print("interrupted", file=sys.stderr)
        return EXIT_FAILURE


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
