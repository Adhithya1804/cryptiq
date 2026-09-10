"""Evidence: attach the exact source span that justifies each rule match.

Evidence must be captured while the snapshot is still on disk. The snapshot
directory is removed when ``ingest_commit`` exits, so anything reading source
has to do it inside that block; ``extract`` therefore takes the root path and
never stores it.
"""

from dataclasses import dataclass
from pathlib import Path

from app.engine.engine import engine_versions
from app.engine.rules import RuleMatch

# A span longer than this is truncated: the excerpt exists so a reviewer can
# see the call, not so the repository can be copied into the database.
MAX_EXCERPT_LINES = 40


@dataclass(frozen=True)
class Evidence:
    """The source span a finding was derived from, as it was at that commit."""

    repository_sha: str
    file_path: str
    start_line: int
    end_line: int
    source_excerpt: str
    rule_id: str
    parser_version: str
    ruleset_version: str
    truncated: bool = False


def extract(match: RuleMatch, root: Path, commit_sha: str) -> Evidence | None:
    """Return the source behind a match, or None if the file cannot be read.

    ``root`` is the live snapshot directory. The lines are taken by the AST
    span the rule recorded, never by searching the text.
    """
    lines = _read_lines(root, match.file_path)
    if lines is None:
        return None

    start = max(match.location.start_line, 1)
    end = min(match.location.end_line, len(lines))
    if start > len(lines):
        return None

    truncated = end - start + 1 > MAX_EXCERPT_LINES
    if truncated:
        end = start + MAX_EXCERPT_LINES - 1

    versions = engine_versions()
    return Evidence(
        repository_sha=commit_sha,
        file_path=match.file_path,
        start_line=start,
        end_line=end,
        source_excerpt="\n".join(lines[start - 1 : end]),
        rule_id=match.rule_id,
        parser_version=versions.parser_version,
        ruleset_version=versions.ruleset_version,
        truncated=truncated,
    )


def _read_lines(root: Path, relative_path: str) -> list[str] | None:
    """Read a snapshot file, refusing any path that leaves the root."""
    resolved_root = root.resolve()
    target = (resolved_root / relative_path).resolve()
    if resolved_root not in target.parents:
        return None
    try:
        return target.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError):
        return None
