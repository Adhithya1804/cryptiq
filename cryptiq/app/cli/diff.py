"""Deterministic finding diff between two local Git commits.

Both commits are analysed by the same deterministic engine, then their
findings are compared **by CRYPTIQ fingerprint**, never by line number. The
fingerprint deliberately excludes line numbers, columns and the commit SHA
(see :mod:`app.engine.fingerprints`), so inserting a line above a call does
not make an unchanged finding look new.

The result is three ordered buckets -- NEW, FIXED, UNCHANGED -- and it is a
pure function of the two commit states: no timestamps, no random ids, no
network, no Gemini.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass

from app.cli.local import local_analysis
from app.cli.results import CliFinding


@dataclass(frozen=True)
class DiffResult:
    """The outcome of comparing two analysed commits."""

    base_sha: str | None
    head_sha: str | None
    repository_label: str
    new: list[CliFinding]
    fixed: list[CliFinding]
    unchanged: list[CliFinding]

    @property
    def has_new(self) -> bool:
        return bool(self.new)


def _dedupe_by_fingerprint(findings: list[CliFinding]) -> dict[str, CliFinding]:
    """Keep the first finding for each fingerprint, in engine order.

    Matches the persistence layer, which stores one row per
    ``(scan, fingerprint)`` and folds later occurrences into the first.
    """
    seen: dict[str, CliFinding] = {}
    for finding in findings:
        key = finding.fingerprint or ""
        if key and key not in seen:
            seen[key] = finding
    return seen


def _ordered(findings: list[CliFinding]) -> list[CliFinding]:
    """Highest priority first, then a stable file/line/fingerprint key."""
    return sorted(
        findings,
        key=lambda f: (
            -f.priority_rank,
            f.file_path or "",
            f.start_line or 0,
            f.fingerprint or "",
        ),
    )


@contextmanager
def run_diff(
    target: str,
    *,
    base: str,
    head: str,
    include_all: bool = False,
) -> Iterator[DiffResult]:
    """Analyse ``base`` and ``head`` locally and yield their fingerprint diff."""
    with local_analysis(target, commit=base, include_all=include_all) as (base_result, base_meta):
        base_findings = _dedupe_by_fingerprint(
            [CliFinding.from_analyzed(f) for f in base_result.findings]
        )
    with local_analysis(target, commit=head, include_all=include_all) as (head_result, head_meta):
        head_findings = _dedupe_by_fingerprint(
            [CliFinding.from_analyzed(f) for f in head_result.findings]
        )

    new = [f for key, f in head_findings.items() if key not in base_findings]
    fixed = [f for key, f in base_findings.items() if key not in head_findings]
    unchanged = [f for key, f in head_findings.items() if key in base_findings]

    yield DiffResult(
        base_sha=base_meta.commit_sha,
        head_sha=head_meta.commit_sha,
        repository_label=head_meta.repository_label,
        new=_ordered(new),
        fixed=_ordered(fixed),
        unchanged=_ordered(unchanged),
    )
