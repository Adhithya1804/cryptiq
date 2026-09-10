"""SARIF 2.1.0 output for the CLI.

The conventions here are the same ones ``.github/scripts/findings_to_sarif.py``
uses for the CI self-scan, so a SARIF file produced by ``cryptiq scan
--format sarif`` and one produced by the CI pipeline describe findings the same
way:

* one rule per ``algorithm`` + ``operation`` pair, id ``cryptiq/<slug>``,
* Cryptiq priority -> SARIF level (high/critical = error, medium = warning,
  low/informational = note),
* repository-relative ``artifactLocation.uri`` (never an absolute local path),
* stable ``partialFingerprints`` so GitHub code scanning can track a finding
  across commits.

The mapping is deterministic: findings are emitted in the order given (the
engine's own order) and rules are sorted, so the same repository state always
produces byte-identical SARIF.
"""

from __future__ import annotations

from typing import Any

from app.cli.results import CliFinding

SARIF_SCHEMA = "https://json.schemastore.org/sarif-2.1.0.json"
SARIF_VERSION = "2.1.0"
TOOL_NAME = "Cryptiq"
INFORMATION_URI = "https://github.com/Invinciblx777/cryptiq"

_LEVEL = {
    "CRITICAL": "error",
    "HIGH": "error",
    "MEDIUM": "warning",
    "LOW": "note",
    "INFORMATIONAL": "note",
}


def _level_for(priority: str | None) -> str:
    return _LEVEL.get((priority or "").strip().upper(), "warning")


def _rule_id(finding: CliFinding) -> str:
    algo = (finding.algorithm or "unknown").strip()
    operation = (finding.operation or "unknown").strip()
    slug = "-".join(part for part in f"{algo} {operation}".split()).lower()
    return f"cryptiq/{slug}"


def _repo_relative(path: str | None) -> str:
    raw = (path or "").strip()
    while raw.startswith("./"):
        raw = raw[2:]
    return raw.lstrip("/") or "UNKNOWN"


def _rule_definition(finding: CliFinding, rule_id: str) -> dict[str, Any]:
    algo = finding.algorithm or "unknown"
    operation = finding.operation or "unknown"
    review_path = finding.review_path or "unspecified"
    name = "".join(w.capitalize() for w in rule_id.split("/", 1)[1].split("-")) or "CryptiqFinding"
    return {
        "id": rule_id,
        "name": name,
        "shortDescription": {"text": f"{algo} used for {operation}"},
        "fullDescription": {
            "text": (
                f"Cryptiq observed {algo} in a {operation} operation. "
                f"Post-quantum review path: {review_path}."
            )
        },
        "defaultConfiguration": {"level": _level_for(finding.priority_level)},
        "properties": {"tags": ["cryptography", "post-quantum", review_path]},
    }


def _result(finding: CliFinding, rule_id: str) -> dict[str, Any]:
    file_path = _repo_relative(finding.file_path)
    start_line = int(finding.start_line or 1) or 1
    end_line = int(finding.end_line or start_line) or start_line
    level = _level_for(finding.priority_level)
    identity = finding.finding_id or finding.fingerprint or ""
    return {
        "ruleId": rule_id,
        "level": level,
        "message": {
            "text": (
                f"{finding.algorithm or 'unknown'} ({finding.api or 'n/a'}) used for "
                f"{finding.operation or 'unknown'}; role {finding.role or 'unknown'}, "
                f"confidence {finding.confidence or 'unknown'}, "
                f"priority {(finding.priority_level or 'unknown').lower()}. "
                f"Review against: {finding.review_path or 'unspecified'}."
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
            "cryptiqFindingId/v1": identity,
            "cryptiqFingerprint/v1": finding.fingerprint or identity,
            "cryptiqFindingKey/v1": f"{file_path}:{start_line}:{rule_id}",
        },
        "properties": {
            "priorityScore": finding.priority_score,
            "isMigrationCandidate": finding.is_migration_candidate,
            "reviewStatus": finding.review_status,
        },
    }


def build_sarif(
    findings: list[CliFinding],
    *,
    automation_id: str = "cryptiq/local",
    tool_version: str | None = None,
) -> dict[str, Any]:
    """Return a SARIF 2.1.0 document for the given findings, in order."""
    rules: dict[str, dict[str, Any]] = {}
    results: list[dict[str, Any]] = []
    for finding in findings:
        rule_id = _rule_id(finding)
        rules.setdefault(rule_id, _rule_definition(finding, rule_id))
        results.append(_result(finding, rule_id))

    driver: dict[str, Any] = {
        "name": TOOL_NAME,
        "informationUri": INFORMATION_URI,
        "rules": [rules[key] for key in sorted(rules)],
    }
    if tool_version:
        driver["version"] = tool_version

    return {
        "$schema": SARIF_SCHEMA,
        "version": SARIF_VERSION,
        "runs": [
            {
                "tool": {"driver": driver},
                "automationDetails": {"id": automation_id},
                "results": results,
                "columnKind": "unicodeCodePoints",
            }
        ],
    }
