"""Human-readable rendering for the CLI.

Compact tables and a finding-detail view that mirrors the API's evidence
hierarchy. Nothing here computes anything; it only formats values that came
from the backend or the in-process engine, and shows ``N/A`` where the value
was ``null`` or an empty list.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.cli.diff import DiffResult
    from app.cli.local import LocalScanMeta
    from app.cli.results import CliFinding

NA = "N/A"


def value_or_na(value: Any) -> str:
    """Render a scalar, using ``N/A`` for ``None`` and empty strings."""
    if value is None:
        return NA
    text = str(value)
    return text if text.strip() else NA


def truncate(value: Any, width: int) -> str:
    """Shorten a cell to ``width`` characters, keeping the tail of a path."""
    text = "" if value is None else str(value)
    if len(text) <= width:
        return text
    if width <= 1:
        return text[:width]
    if "/" in text and width >= 4:
        # Paths read better truncated from the left: keep the file name.
        return "..." + text[-(width - 3):]
    return text[: width - 1] + "…"


def render_table(
    headers: Sequence[str],
    rows: Iterable[Sequence[Any]],
    *,
    max_widths: Sequence[int] | None = None,
) -> str:
    """Return a plain-text table. Columns are padded to their widest cell."""
    body = [
        [
            truncate(cell, max_widths[i]) if max_widths and i < len(max_widths) else str(
                "" if cell is None else cell
            )
            for i, cell in enumerate(row)
        ]
        for row in rows
    ]
    widths = [len(header) for header in headers]
    for row in body:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], len(cell))

    def _line(cells: Sequence[str]) -> str:
        return "  ".join(cell.ljust(widths[i]) for i, cell in enumerate(cells)).rstrip()

    lines = [_line(headers), _line(["-" * w for w in widths])]
    lines.extend(_line(row) for row in body)
    if not body:
        lines.append("(no rows)")
    return "\n".join(lines)


def _section(title: str, pairs: Sequence[tuple[str, Any]]) -> list[str]:
    lines = [title]
    label_width = max((len(label) for label, _ in pairs), default=0)
    for label, value in pairs:
        if isinstance(value, list):
            if not value:
                lines.append(f"  {label.ljust(label_width)}  {NA}")
            else:
                lines.append(f"  {label.ljust(label_width)}  {value[0]}")
                for extra in value[1:]:
                    lines.append(f"  {' ' * label_width}  {extra}")
        else:
            lines.append(f"  {label.ljust(label_width)}  {value_or_na(value)}")
    return lines


def render_finding_detail(finding: dict[str, Any]) -> str:
    """Render one finding in the API's Observed/Inference/Migration/... order."""
    observed = finding.get("observed") or {}
    location = observed.get("location") or {}
    inference = finding.get("inference") or {}
    migration = finding.get("migration") or {}
    impact = finding.get("impact") or {}
    priority = finding.get("priority") or {}
    review = finding.get("review")

    line_range = value_or_na(location.get("start_line"))
    if location.get("end_line") not in (None, location.get("start_line")):
        line_range = f"{location.get('start_line')}-{location.get('end_line')}"

    blocks: list[list[str]] = []
    blocks.append(
        [f"Finding {finding.get('id', NA)}", f"  scan {value_or_na(finding.get('scan_id'))}"]
    )
    blocks.append(
        _section(
            "Observed",
            [
                ("rule id", observed.get("rule_id")),
                ("algorithm", observed.get("algorithm")),
                ("primitive", observed.get("primitive")),
                ("library", observed.get("library")),
                ("api", observed.get("api")),
                ("operation", observed.get("operation")),
                ("file", location.get("file_path")),
                ("lines", line_range),
                ("excerpt", observed.get("source_excerpt")),
            ],
        )
    )
    blocks.append(
        _section(
            "Inference",
            [
                ("role", inference.get("role")),
                ("rationale", inference.get("rationale") or []),
                ("confidence", inference.get("confidence")),
                ("evidence basis", inference.get("evidence_basis")),
            ],
        )
    )
    blocks.append(
        _section(
            "Migration",
            [
                ("review path", migration.get("review_path")),
                ("rationale", migration.get("rationale")),
                ("migration candidate", migration.get("is_migration_candidate")),
                ("current", migration.get("current")),
            ],
        )
    )
    blocks.append(
        _section(
            "Impact",
            [
                ("scope", impact.get("scope")),
                ("node count", impact.get("node_count")),
                ("nodes", impact.get("nodes") or []),
                ("relationships", impact.get("relationships") or []),
            ],
        )
    )
    blocks.append(
        _section(
            "Priority",
            [
                ("level", priority.get("level")),
                ("score", priority.get("score")),
                ("reasons", priority.get("reasons") or []),
            ],
        )
    )
    if review:
        blocks.append(
            _section(
                "Review",
                [
                    ("status", review.get("status")),
                    ("assignee", review.get("assigned_to")),
                    ("note", review.get("note")),
                    ("updated", review.get("updated_at")),
                ],
            )
        )
    else:
        blocks.append(["Review", f"  {NA} (no review opened)"])

    return "\n\n".join("\n".join(block) for block in blocks)


# --------------------------------------------------------------------------- #
# common CLI result model (local + remote)
# --------------------------------------------------------------------------- #

_PRIORITY_ORDER = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3, "INFORMATIONAL": 4}


def render_cli_finding(finding: CliFinding) -> str:
    """Render one normalised finding in OBSERVED -> REVIEW order.

    Same block order the API uses and the task specifies. Values the engine or
    API did not provide show as ``N/A``; nothing is invented.
    """
    line_range = value_or_na(finding.start_line)
    if finding.end_line not in (None, finding.start_line):
        line_range = f"{finding.start_line}-{finding.end_line}"

    ident = finding.finding_id or finding.fingerprint or NA
    blocks: list[list[str]] = [
        [f"Finding {ident}", f"  fingerprint {value_or_na(finding.fingerprint)}"],
        _section(
            "OBSERVED",
            [
                ("Rule", finding.rule_id),
                ("Algorithm", finding.algorithm),
                ("API", finding.api),
                ("Primitive", finding.primitive),
                ("Library", finding.library),
                ("Operation", finding.operation),
                ("File", finding.file_path),
                ("Lines", line_range),
                ("Evidence", finding.source_excerpt),
            ],
        ),
        _section(
            "INFERENCE",
            [
                ("Role", finding.role),
                ("Confidence", finding.confidence),
                ("Basis", finding.evidence_basis),
                ("Rationale", list(finding.role_rationale)),
            ],
        ),
        _section(
            "MIGRATION REVIEW",
            [
                ("PQC Family", finding.review_path),
                ("Candidate", finding.is_migration_candidate),
                ("Current", finding.migration_current),
                ("Standards", finding.migration_rationale),
            ],
        ),
        _section(
            "IMPACT",
            [
                ("Scope", finding.impact_scope),
                ("Nodes", list(finding.impact_nodes)),
                ("Relationships", list(finding.impact_relationships)),
            ],
        ),
        _section(
            "MIGRATION REVIEW PRIORITY",
            [
                ("Level", finding.priority_level),
                ("Score", finding.priority_score),
                ("Reasons", list(finding.priority_reasons)),
            ],
        ),
        _section(
            "REVIEW",
            [
                ("Status", finding.review_status),
                ("Assignee", finding.review_assignee),
                ("Note", finding.review_note),
                ("Updated", finding.review_updated_at),
            ],
        ),
    ]
    if finding.contextual_assessment:
        ca = finding.contextual_assessment
        sources = ca.get("knowledge_sources") or []
        citations = [f"{s.get('document_id')} ({s.get('section')})" for s in sources[:3]]
        blocks.append(
            _section(
                "CONTEXT-AWARE MIGRATION ASSESSMENT",
                [
                    ("Decision", ca.get("assessment")),
                    ("Confidence", ca.get("confidence")),
                    ("Contextual Role", ca.get("contextual_role")),
                    ("PQC Migration Required", "Yes" if ca.get("pqc_migration_required") else "No"),
                    ("Candidate", ca.get("migration_candidate")),
                    ("Rationale", ca.get("rationale")),
                    ("Engineering Trade-offs", ca.get("engineering_tradeoffs") or []),
                    ("Authoritative Citations", citations or []),
                    ("Limitations", ca.get("limitations") or []),
                ],
            )
        )
    return "\n\n".join("\n".join(block) for block in blocks)


def render_cli_findings_table(findings: Sequence[CliFinding]) -> str:
    """A compact one-row-per-finding table for the scan summary."""
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


def _priority_counts(findings: Sequence[CliFinding]) -> str:
    counts: dict[str, int] = {}
    for finding in findings:
        key = (finding.priority_level or "UNKNOWN").upper()
        counts[key] = counts.get(key, 0) + 1
    ordered = sorted(counts.items(), key=lambda kv: _PRIORITY_ORDER.get(kv[0], 99))
    return "  ".join(f"{name.lower()}={count}" for name, count in ordered) or "none"


def render_local_summary(
    meta: LocalScanMeta,
    findings: Sequence[CliFinding],
    *,
    files_analyzed: int,
    total_files: int,
) -> str:
    """The human report for ``cryptiq scan`` in local mode."""
    lines = [
        "CRYPTIQ SCAN",
        f"Target:      {meta.target}",
        f"Repository:  {meta.repository_label}",
        f"Mode:        {meta.mode} (offline, local engine)",
        f"Commit:      {value_or_na(meta.commit_sha)}",
    ]
    if meta.dirty:
        lines.append("Note:        working tree has uncommitted changes")
    lines += [
        f"Files:       {files_analyzed} analyzed / {total_files} discovered",
        f"Findings:    {len(findings)}  ({_priority_counts(findings)})",
        "",
        render_cli_findings_table(findings),
    ]
    return "\n".join(lines)


def _diff_row(finding: CliFinding) -> str:
    return (
        f"  {value_or_na(finding.priority_level):<8} "
        f"{value_or_na(finding.algorithm):<10} "
        f"{value_or_na(finding.file_path)}:{value_or_na(finding.start_line)}"
    )


def render_diff(diff: DiffResult) -> str:
    """Render NEW / FIXED / UNCHANGED buckets, deterministic order."""
    lines = [
        "CRYPTIQ DIFF",
        f"Repository: {diff.repository_label}",
        f"Base:       {value_or_na(diff.base_sha)}",
        f"Head:       {value_or_na(diff.head_sha)}",
        "",
        f"NEW ({len(diff.new)})",
    ]
    lines += [_diff_row(f) for f in diff.new] or ["  (none)"]
    lines += ["", f"FIXED ({len(diff.fixed)})"]
    lines += [_diff_row(f) for f in diff.fixed] or ["  (none)"]
    lines += ["", f"UNCHANGED ({len(diff.unchanged)})"]
    lines += [_diff_row(f) for f in diff.unchanged] or ["  (none)"]
    return "\n".join(lines)
