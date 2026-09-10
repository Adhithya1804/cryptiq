#!/usr/bin/env python3
"""Convert a completed Cryptiq scan's findings into a SARIF 2.1.0 file.

Used by the `cryptiq-self-scan` CI job:

    repo -> Cryptiq CLI (submit + poll) -> THIS SCRIPT -> SARIF -> GitHub code scanning

It talks to the running backend directly (`GET /scans/{id}/findings`, paged),
so it needs no third-party packages -- only the standard library.

The mapping is deterministic: the same scan always produces byte-identical
SARIF (findings are emitted in the engine's own order; rules are sorted).
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request

PAGE_SIZE = 200  # server cap (scans.MAX_PAGE_SIZE)

# Cryptiq priority -> SARIF result level.
_LEVEL = {
    "critical": "error",
    "high": "error",
    "medium": "warning",
    "low": "note",
    "informational": "note",
}


def _get(url: str) -> dict:
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:  # localhost API only
            return json.load(resp)
    except urllib.error.HTTPError as exc:  # pragma: no cover - CI diagnostics
        sys.exit(f"HTTP {exc.code} fetching {url}: {exc.read().decode('utf-8', 'replace')}")
    except urllib.error.URLError as exc:  # pragma: no cover
        sys.exit(f"Could not reach {url}: {exc}")


def fetch_findings(api_url: str, scan_id: str) -> list[dict]:
    base = api_url.rstrip("/")
    first = _get(f"{base}/scans/{scan_id}/findings?page=1&page_size={PAGE_SIZE}")
    items = list(first.get("items", []))
    pages = int(first.get("pages", 1))
    for page in range(2, pages + 1):
        items.extend(
            _get(f"{base}/scans/{scan_id}/findings?page={page}&page_size={PAGE_SIZE}").get(
                "items", []
            )
        )
    return items


def _rule_id(finding: dict) -> str:
    algo = str(finding.get("algorithm") or "unknown").strip()
    operation = str(finding.get("operation") or "unknown").strip()
    slug = "-".join(part for part in (algo + " " + operation).split()).lower()
    return f"cryptiq/{slug}"


def build_sarif(findings: list[dict], scan_id: str) -> dict:
    rules: dict[str, dict] = {}
    results: list[dict] = []

    for finding in findings:
        rule_id = _rule_id(finding)
        algo = finding.get("algorithm") or "unknown"
        operation = finding.get("operation") or "unknown"
        review_path = finding.get("review_path") or "unspecified"

        if rule_id not in rules:
            rules[rule_id] = {
                "id": rule_id,
                "name": "".join(
                    w.capitalize() for w in rule_id.split("/", 1)[1].split("-")
                )
                or "CryptiqFinding",
                "shortDescription": {
                    "text": f"{algo} used for {operation}"
                },
                "fullDescription": {
                    "text": (
                        f"Cryptiq observed {algo} in a {operation} operation. "
                        f"Post-quantum review path: {review_path}."
                    )
                },
                "defaultConfiguration": {"level": _LEVEL.get(
                    str(finding.get("priority", "")).lower(), "warning"
                )},
                "properties": {
                    "tags": ["cryptography", "post-quantum", review_path],
                },
            }

        priority = str(finding.get("priority") or "").lower()
        raw_path = str(finding.get("file_path") or "").strip()
        while raw_path.startswith("./"):
            raw_path = raw_path[2:]
        file_path = raw_path.lstrip("/") or "UNKNOWN"
        start_line = int(finding.get("start_line") or 1) or 1
        end_line = int(finding.get("end_line") or start_line) or start_line
        finding_id = str(finding.get("id") or "")

        results.append(
            {
                "ruleId": rule_id,
                "level": _LEVEL.get(priority, "warning"),
                "message": {
                    "text": (
                        f"{algo} ({finding.get('api') or 'n/a'}) used for "
                        f"{operation}; role {finding.get('role') or 'unknown'}, "
                        f"confidence {finding.get('confidence') or 'unknown'}, "
                        f"priority {priority or 'unknown'}. "
                        f"Review against: {review_path}."
                    )
                },
                "locations": [
                    {
                        "physicalLocation": {
                            "artifactLocation": {"uri": file_path},
                            "region": {
                                "startLine": start_line,
                                "endLine": max(end_line, start_line),
                            },
                        }
                    }
                ],
                "partialFingerprints": {
                    "cryptiqFindingId/v1": finding_id,
                    "cryptiqFindingKey/v1": f"{file_path}:{start_line}:{rule_id}",
                },
                "properties": {
                    "priorityScore": finding.get("priority_score"),
                    "isMigrationCandidate": finding.get("is_migration_candidate"),
                    "reviewStatus": finding.get("review_status"),
                },
            }
        )

    return {
        "$schema": "https://json.schemastore.org/sarif-2.1.0.json",
        "version": "2.1.0",
        "runs": [
            {
                "tool": {
                    "driver": {
                        "name": "Cryptiq",
                        "informationUri": "https://github.com/Invinciblx777/cryptiq",
                        "rules": [rules[k] for k in sorted(rules)],
                    }
                },
                "automationDetails": {"id": f"cryptiq-self-scan/{scan_id}"},
                "results": results,
                "columnKind": "unicodeCodePoints",
            }
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api-url", required=True, help="e.g. http://127.0.0.1:8000/api/v1")
    parser.add_argument("--scan-id", required=True)
    parser.add_argument(
        "--repo-root",
        default=".",
        help="Reserved for path normalization; findings paths are already repo-relative.",
    )
    parser.add_argument("--output", required=True)
    args = parser.parse_args(argv)

    findings = fetch_findings(args.api_url, args.scan_id)
    sarif = build_sarif(findings, args.scan_id)

    with open(args.output, "w", encoding="utf-8") as handle:
        json.dump(sarif, handle, indent=2, sort_keys=False)
        handle.write("\n")

    print(
        f"Wrote {args.output}: {len(findings)} findings, "
        f"{len(sarif['runs'][0]['tool']['driver']['rules'])} rules."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
