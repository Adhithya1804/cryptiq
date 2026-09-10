"""Writing a finished engine result into the database.

The engine's :class:`~app.engine.pipeline.AnalysisResult` is the source of
truth. This module reshapes it into rows; it never recomputes a role, a
priority or a fingerprint, and it never re-reads source. Every value written
here was established by a deterministic stage upstream.

A finding that is a post-quantum migration candidate is given an OPEN
:class:`~app.db.models.review_item.ReviewItem` as it is written, so the review
queue is populated the moment a scan completes rather than only after a human
has already touched each finding.
"""

from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from app.db.models.enums import (
    Confidence,
    CryptographicRole,
    ImpactNodeType,
    ImpactRelationship,
    ReviewPriority,
    ReviewStatus,
)
from app.db.models.evidence import Evidence
from app.db.models.finding import Finding
from app.db.models.impact_node import ImpactNode
from app.db.models.review_item import ReviewItem
from app.db.models.scan import Scan
from app.engine.pipeline import AnalysisResult, AnalyzedFinding

logger = logging.getLogger(__name__)


def _confidence(value: str) -> Confidence:
    """Map an engine confidence token onto the persisted vocabulary."""
    try:
        return Confidence(value)
    except ValueError:
        # ``MatchConfidence.UNKNOWN`` is never emitted per the contract, but a
        # bare finding must still store a value the column accepts.
        return Confidence.LOW


def _finding_row(analyzed: AnalyzedFinding, scan_id: str) -> Finding:
    match = analyzed.match
    location = match.location
    finding = Finding(
        scan_id=scan_id,
        fingerprint=analyzed.fingerprint,
        algorithm=match.algorithm,
        primitive=match.primitive,
        library=match.library,
        api=match.api,
        operation=match.operation.value,
        file_path=match.file_path,
        start_line=location.start_line,
        end_line=location.end_line,
        start_column=location.start_column,
        end_column=location.end_column,
        role=CryptographicRole(analyzed.role.role.value),
        confidence=_confidence(match.confidence.value),
        priority=ReviewPriority(analyzed.priority.level.value),
        priority_score=analyzed.priority.score,
        priority_reasons=list(analyzed.priority.reasons),
        role_rationale=analyzed.role.rationale,
    )
    finding.evidence = Evidence(
        repository_sha=analyzed.evidence.repository_sha,
        file_path=analyzed.evidence.file_path,
        start_line=analyzed.evidence.start_line,
        end_line=analyzed.evidence.end_line,
        source_excerpt=analyzed.evidence.source_excerpt,
        rule_id=analyzed.evidence.rule_id,
        parser_version=analyzed.evidence.parser_version,
        ruleset_version=analyzed.evidence.ruleset_version,
    )
    finding.impact_nodes = [
        ImpactNode(
            node_type=ImpactNodeType(node.node_type.value),
            label=node.label,
            relationship_type=(
                ImpactRelationship(node.relationship.value)
                if node.relationship is not None
                else None
            ),
            confidence=_confidence(node.confidence.value),
        )
        for node in analyzed.impact.nodes
    ]
    if analyzed.pqc.is_migration_candidate:
        finding.review_items = [ReviewItem(status=ReviewStatus.OPEN)]
    return finding


def persist_analysis(session: Session, scan: Scan, result: AnalysisResult) -> None:
    """Write every finding of a completed analysis and update the scan counts.

    A fingerprint is the identity of one *logical* finding: it deliberately
    excludes line numbers, so the same construct used twice in one function
    produces two engine matches with one fingerprint. The database enforces one
    row per (scan, fingerprint); the first occurrence in the engine's
    deterministic order is kept and the rest are folded into it.

    The caller owns the transaction: this adds rows and flushes, but does not
    commit.
    """
    seen: set[str] = set()
    written = 0
    for analyzed in result.findings:
        if analyzed.fingerprint in seen:
            continue
        seen.add(analyzed.fingerprint)
        session.add(_finding_row(analyzed, scan.id))
        written += 1

    scan.file_count = result.total_files
    scan.analyzed_file_count = result.analyzed_files
    scan.skipped_file_count = result.skipped_files
    scan.finding_count = written
    session.flush()
    logger.info(
        "persisted %d findings (%d engine matches) for scan %s",
        written,
        len(result.findings),
        scan.id,
    )
