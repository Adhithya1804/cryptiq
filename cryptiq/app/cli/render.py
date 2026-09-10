"""Human-readable rendering for the CLI.

Compact tables and a finding-detail view that mirrors the API's evidence
hierarchy. Nothing here computes anything; it only formats values that came
from the backend, and shows ``N/A`` where the backend sent ``null`` or an
empty list.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import Any

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
