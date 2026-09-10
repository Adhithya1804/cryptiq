"""``cryptiq`` command-line interface.

A thin client over the running FastAPI backend. Every command maps to one or
more ``/api/v1`` calls; no analysis, persistence or review logic is
reimplemented here.

Commands
--------
* ``cryptiq scan <repo_url> <commit_sha>``   -- submit an exact scan
* ``cryptiq scan-status <scan_id>``          -- monitor a scan
* ``cryptiq findings <scan_id>``             -- list findings (server-filtered)
* ``cryptiq finding <finding_id>``           -- one finding, full evidence
* ``cryptiq review-queue``                   -- the global review queue
* ``cryptiq review-update <review_id>``      -- move a review item (if allowed)
* ``cryptiq demo``                           -- run the acceptance scan end to end

Exit codes
----------
* 0 success
* 1 general / user-facing failure
* 2 invalid command or arguments
* 3 scan failed
* 4 requested resource not found
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections.abc import Callable
from typing import Any

from app.cli.client import (
    EXIT_FAILURE,
    EXIT_OK,
    EXIT_SCAN_FAILED,
    EXIT_USAGE,
    CliError,
    CryptiqClient,
)
from app.cli.render import render_finding_detail, render_table, value_or_na

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

_ACTIVE_SCAN_STATES = {"QUEUED", "RUNNING"}


# --------------------------------------------------------------------------- #
# output helpers
# --------------------------------------------------------------------------- #


def _emit(data: Any, *, as_json: bool, text: str) -> None:
    if as_json:
        print(json.dumps(data, indent=2, sort_keys=True))
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


# --------------------------------------------------------------------------- #
# commands
# --------------------------------------------------------------------------- #


def cmd_scan(client: CryptiqClient, args: argparse.Namespace) -> int:
    inspection, cached = client.create_scan(args.repository_url, args.commit_sha)
    if args.json:
        print(json.dumps(inspection, indent=2, sort_keys=True))
        return EXIT_OK

    lines = [
        "Cryptiq Scan",
        f"Repository: {_repo_label(inspection.get('repository'))}",
        f"Commit: {value_or_na(inspection.get('commit_sha'))}",
    ]
    if cached:
        lines.append("Status: CACHED")
        lines.append(f"Scan ID: {value_or_na(inspection.get('id'))}")
        lines.append("Existing result reused.")
    else:
        lines.append(f"Status: {value_or_na(inspection.get('status')) or 'QUEUED'}")
        lines.append(f"Scan ID: {value_or_na(inspection.get('id'))}")
    print("\n".join(lines))
    return EXIT_OK


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


def cmd_scan_status(client: CryptiqClient, args: argparse.Namespace) -> int:
    inspection = client.get_scan(args.scan_id)
    _emit(
        inspection,
        as_json=args.json,
        text="\n".join(_scan_status_lines(inspection)),
    )
    return EXIT_SCAN_FAILED if inspection.get("status") == "FAILED" else EXIT_OK


def _findings_table(items: list[dict[str, Any]]) -> str:
    headers = [
        "FINDING ID",
        "ALGORITHM",
        "OPERATION",
        "ROLE",
        "PRIORITY",
        "CONF",
        "FILE",
        "LINE",
        "REVIEW PATH",
    ]
    rows = [
        [
            item.get("id"),
            item.get("algorithm"),
            item.get("operation"),
            item.get("role"),
            item.get("priority"),
            item.get("confidence"),
            item.get("file_path"),
            item.get("start_line"),
            item.get("review_path"),
        ]
        for item in items
    ]
    widths = [36, 10, 16, 20, 13, 6, 34, 6, 26]
    return render_table(headers, rows, max_widths=widths)


def cmd_findings(client: CryptiqClient, args: argparse.Namespace) -> int:
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
        print(json.dumps(page, indent=2, sort_keys=True))
        return EXIT_OK

    items = page.get("items", [])
    text = "\n".join(
        [
            _findings_table(items),
            "",
            f"Page {page.get('page', 1)} / {page.get('pages', 1)}",
            f"Total findings: {page.get('total', len(items))}",
        ]
    )
    print(text)
    return EXIT_OK


def cmd_finding(client: CryptiqClient, args: argparse.Namespace) -> int:
    finding = client.get_finding(args.finding_id)
    _emit(finding, as_json=args.json, text=render_finding_detail(finding))
    return EXIT_OK


def _queue_table(items: list[dict[str, Any]]) -> str:
    headers = [
        "REVIEW ID",
        "FINDING ID",
        "ALGORITHM",
        "ROLE",
        "PRIORITY",
        "STATUS",
        "FILE",
        "LINE",
    ]
    rows = [
        [
            item.get("review_id"),
            item.get("finding_id"),
            item.get("algorithm"),
            item.get("role"),
            item.get("priority"),
            item.get("status"),
            item.get("file_path"),
            item.get("start_line"),
        ]
        for item in items
    ]
    widths = [36, 36, 10, 20, 13, 16, 34, 6]
    return render_table(headers, rows, max_widths=widths)


def cmd_review_queue(client: CryptiqClient, args: argparse.Namespace) -> int:
    envelope = client.review_queue(
        page=args.page,
        page_size=args.page_size,
        priority=args.priority,
        algorithm=args.algorithm,
        role=args.role,
        status=args.status,
    )
    if args.json:
        print(json.dumps(envelope, indent=2, sort_keys=True))
        return EXIT_OK

    items = envelope.get("items", [])
    text = "\n".join(
        [
            _queue_table(items),
            "",
            f"Review items: {envelope.get('total', len(items))}",
        ]
    )
    print(text)
    return EXIT_OK


def cmd_review_update(client: CryptiqClient, args: argparse.Namespace) -> int:
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


def cmd_demo(client: CryptiqClient, args: argparse.Namespace) -> int:
    out: dict[str, Any] = {"repository": DEMO_REPOSITORY, "commit": DEMO_COMMIT}
    if not args.json:
        print("Cryptiq demo")
        print(f"Repository: {DEMO_REPOSITORY}")
        print(f"Commit:     {DEMO_COMMIT}")

    inspection, cached = client.create_scan(DEMO_REPOSITORY, DEMO_COMMIT)
    scan_id = inspection["id"]
    out["scan_id"] = scan_id
    out["cached"] = cached
    if not args.json:
        if cached:
            print(f"\nCached result reused. Scan ID: {scan_id}")
        else:
            print(f"\nQueued. Scan ID: {scan_id}")

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
            print(json.dumps(out, indent=2, sort_keys=True))
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
        print(json.dumps(out, indent=2, sort_keys=True))
        return EXIT_OK

    print(f"\nStatus: {status}")
    print(f"Findings: {value_or_na(inspection.get('findings_count'))}")
    print(f"\nSample findings (first {args.sample_size}):")
    print(_findings_table(findings_page.get("items", [])))
    print("\nMigration candidates (HIGH priority, first "
          f"{args.sample_size}):")
    print(_findings_table(out["migration_candidates"]))
    print(f"\nReview queue items: {value_or_na(queue.get('total'))}")
    return EXIT_OK


# --------------------------------------------------------------------------- #
# argument parser
# --------------------------------------------------------------------------- #


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cryptiq",
        description="Developer/demo client for the Cryptiq analysis backend.",
    )
    parser.add_argument(
        "--api-url",
        default=None,
        help="Base URL of the Cryptiq API "
        "(default: $CRYPTIQ_API_URL or http://localhost:8000/api/v1).",
    )
    sub = parser.add_subparsers(dest="command", metavar="<command>")
    sub.required = True

    def _add_json(p: argparse.ArgumentParser) -> None:
        p.add_argument(
            "--json", action="store_true", help="Emit the raw API JSON instead of text."
        )

    p_scan = sub.add_parser("scan", help="Submit an exact repository + commit scan.")
    p_scan.add_argument("repository_url", help="https://github.com/{owner}/{repo}")
    p_scan.add_argument("commit_sha", help="7-40 hex characters (short or full).")
    _add_json(p_scan)
    p_scan.set_defaults(func=cmd_scan)

    p_status = sub.add_parser("scan-status", help="Show a scan's status.")
    p_status.add_argument("scan_id")
    _add_json(p_status)
    p_status.set_defaults(func=cmd_scan_status)

    p_findings = sub.add_parser("findings", help="List a scan's findings.")
    p_findings.add_argument("scan_id")
    p_findings.add_argument("--page", type=int, default=1)
    p_findings.add_argument("--page-size", type=int, default=50, dest="page_size")
    p_findings.add_argument("--priority", choices=PRIORITY_CHOICES)
    p_findings.add_argument("--algorithm", help="Case-insensitive substring match.")
    p_findings.add_argument("--role", choices=ROLE_CHOICES)
    p_findings.add_argument(
        "--status", choices=REVIEW_STATUS_CHOICES, help="Filter by review status."
    )
    p_findings.add_argument("--confidence", choices=CONFIDENCE_CHOICES)
    _add_json(p_findings)
    p_findings.set_defaults(func=cmd_findings)

    p_finding = sub.add_parser("finding", help="Show one finding in full.")
    p_finding.add_argument("finding_id")
    _add_json(p_finding)
    p_finding.set_defaults(func=cmd_finding)

    p_queue = sub.add_parser("review-queue", help="Show the global review queue.")
    p_queue.add_argument("--page", type=int, default=None)
    p_queue.add_argument("--page-size", type=int, default=50, dest="page_size")
    p_queue.add_argument("--priority", choices=PRIORITY_CHOICES)
    p_queue.add_argument("--algorithm", help="Case-insensitive substring match.")
    p_queue.add_argument("--role", choices=ROLE_CHOICES)
    p_queue.add_argument("--status", choices=REVIEW_STATUS_CHOICES)
    _add_json(p_queue)
    p_queue.set_defaults(func=cmd_review_queue)

    p_review = sub.add_parser(
        "review-update",
        help="Move one review item through a valid workflow transition.",
    )
    p_review.add_argument("review_id")
    p_review.add_argument("--status", choices=REVIEW_STATUS_CHOICES)
    p_review.add_argument("--assignee", help="Set the assignee (empty string clears).")
    p_review.add_argument("--note", help="Set the note (empty string clears).")
    _add_json(p_review)
    p_review.set_defaults(func=cmd_review_update)

    p_demo = sub.add_parser(
        "demo", help="Run the pyca/cryptography acceptance scan end to end."
    )
    p_demo.add_argument("--poll-interval", type=float, default=2.0, dest="poll_interval")
    p_demo.add_argument("--timeout", type=float, default=600.0)
    p_demo.add_argument("--sample-size", type=int, default=5, dest="sample_size")
    _add_json(p_demo)
    p_demo.set_defaults(func=cmd_demo)

    return parser


def main(
    argv: list[str] | None = None,
    *,
    client_factory: Callable[[str | None], CryptiqClient] = CryptiqClient,
) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        with client_factory(args.api_url) as client:
            return args.func(client, args)
    except CliError as exc:
        print(f"error: {exc.message}", file=sys.stderr)
        return exc.exit_code
    except KeyboardInterrupt:  # pragma: no cover - interactive only
        print("interrupted", file=sys.stderr)
        return EXIT_FAILURE


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
