"""Persisted rows -> the HTTP wire contract in ``app.schemas.api``.

This layer only reshapes. The one thing it computes is the post-quantum
review path, and that is a pure lookup on the algorithm and the already-stored
role (:func:`app.engine.pqc.map_review_path`), not a re-analysis: the same
call the engine made, replayed on stored inputs so the mapping does not have
to be duplicated in a column.
"""

from __future__ import annotations

from datetime import datetime

from app.config import get_settings
from app.db.models.finding import Finding
from app.db.models.repository import Repository
from app.db.models.review_item import ReviewItem
from app.db.models.scan import Scan
from app.engine.pqc import map_review_path
from app.engine.roles import CryptographicRole as EngineRole
from app.schemas.api import (
    ApiFindingDto,
    ApiFindingSummaryDto,
    ApiImpactBlock,
    ApiInferenceBlock,
    ApiInspectionDto,
    ApiLocation,
    ApiMigrationBlock,
    ApiObservedBlock,
    ApiPriorityBlock,
    ApiRepositoryDto,
    ApiRepositoryRef,
    ApiReviewBlock,
    ApiReviewQueueItemDto,
    ApiSeverityBreakdown,
)

LANGUAGE = "Python"
IMPACT_SCOPE = "STATICALLY_OBSERVED"

# Priority bands the engine can emit, folded onto the four severity buckets the
# Projects and Inspection screens show. The engine produces only HIGH/MEDIUM/LOW
# today; CRITICAL and INFORMATIONAL are mapped so the UI keeps working if they
# ever appear.
_SEVERITY_BUCKET = {
    "CRITICAL": "critical",
    "HIGH": "high",
    "MEDIUM": "medium",
    "LOW": "low",
    "INFORMATIONAL": "low",
}


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def repository_ref(repository: Repository) -> ApiRepositoryRef:
    return ApiRepositoryRef(
        provider=repository.provider,
        owner=repository.owner,
        name=repository.name,
        url=repository.canonical_url,
    )


def severity_breakdown(counts: dict[str, int]) -> ApiSeverityBreakdown:
    """Fold a ``{priority band: count}`` mapping onto the four UI buckets."""
    folded = {"critical": 0, "high": 0, "medium": 0, "low": 0}
    for band, count in counts.items():
        folded[_SEVERITY_BUCKET.get(band, "low")] += count
    return ApiSeverityBreakdown(**folded)


def inspection_dto(
    scan: Scan,
    repository: Repository,
    *,
    severity: ApiSeverityBreakdown | None = None,
) -> ApiInspectionDto:
    started, completed = scan.started_at, scan.completed_at
    duration_ms: int | None = None
    if started is not None and completed is not None:
        duration_ms = max(int((completed - started).total_seconds() * 1000), 0)
    return ApiInspectionDto(
        id=scan.id,
        repository_id=scan.repository_id,
        repository=repository_ref(repository),
        language=LANGUAGE,
        commit_sha=scan.commit_sha,
        status=scan.status.value,
        started_at=_iso(started),
        completed_at=_iso(completed),
        duration_ms=duration_ms,
        files_analyzed=scan.analyzed_file_count or None,
        findings_count=scan.finding_count,
        severity=severity or ApiSeverityBreakdown(),
        error_code=scan.error_code,
        error_message=scan.error_message,
    )


def repository_dto(
    repository: Repository,
    *,
    latest: Scan | None,
    findings_count: int | None,
) -> ApiRepositoryDto:
    return ApiRepositoryDto(
        id=repository.id,
        repository=repository_ref(repository),
        language=LANGUAGE,
        last_inspected_at=_iso(latest.created_at) if latest is not None else None,
        latest_inspection_status=latest.status.value if latest is not None else None,
        findings_count=findings_count,
    )


def _migration_for(finding: Finding) -> tuple[str, str, bool]:
    assessment = map_review_path(finding.algorithm, EngineRole(finding.role.value))
    return (
        assessment.review_path.value,
        assessment.rationale,
        assessment.is_migration_candidate,
    )


def _review_of(finding: Finding) -> ReviewItem | None:
    if not finding.review_items:
        return None
    return max(finding.review_items, key=lambda item: item.created_at)


def review_block(review: ReviewItem) -> ApiReviewBlock:
    return ApiReviewBlock(
        id=review.id,
        status=review.status.value,
        assigned_to=review.assigned_to,
        note=review.note,
        created_at=_iso(review.created_at),
        updated_at=_iso(review.updated_at),
    )


def finding_dto(finding: Finding, scan: Scan, repository: Repository) -> ApiFindingDto:
    evidence = finding.evidence
    review_path, migration_rationale, is_candidate = _migration_for(finding)
    review = _review_of(finding)
    return ApiFindingDto(
        id=finding.id,
        scan_id=finding.scan_id,
        fingerprint=finding.fingerprint,
        repository=repository_ref(repository),
        commit_sha=scan.commit_sha,
        language=LANGUAGE,
        observed=ApiObservedBlock(
            rule_id=evidence.rule_id,
            algorithm=finding.algorithm,
            api=finding.api,
            primitive=finding.primitive,
            library=finding.library,
            operation=finding.operation,
            location=ApiLocation(
                file_path=finding.file_path,
                start_line=finding.start_line,
                end_line=finding.end_line,
                start_column=finding.start_column,
                end_column=finding.end_column,
            ),
            source_excerpt=evidence.source_excerpt,
            enclosing_function=evidence.enclosing_function,
            enclosing_class=evidence.enclosing_class,
            parser_version=evidence.parser_version,
            ruleset_version=evidence.ruleset_version,
        ),
        inference=ApiInferenceBlock(
            role=finding.role.value,
            rationale=[finding.role_rationale] if finding.role_rationale else [],
            confidence=finding.confidence.value,
            evidence_basis=finding.evidence_basis,
        ),
        migration=ApiMigrationBlock(
            review_path=review_path,
            rationale=migration_rationale,
            is_migration_candidate=is_candidate,
            pqc_ruleset_version=get_settings().pqc_ruleset_version,
            current=finding.algorithm,
        ),
        impact=ApiImpactBlock(
            scope=IMPACT_SCOPE,
            node_count=len(finding.impact_nodes),
            nodes=[node.label for node in finding.impact_nodes],
            relationships=[
                node.relationship_type.value
                for node in finding.impact_nodes
                if node.relationship_type is not None
            ],
        ),
        priority=ApiPriorityBlock(
            level=finding.priority.value,
            score=finding.priority_score,
            reasons=list(finding.priority_reasons or []),
        ),
        review=review_block(review) if review is not None else None,
        ai_explanation_available=bool(get_settings().gemini_api_key),
    )


def finding_summary_dto(finding: Finding) -> ApiFindingSummaryDto:
    review_path, _, is_candidate = _migration_for(finding)
    review = _review_of(finding)
    return ApiFindingSummaryDto(
        id=finding.id,
        scan_id=finding.scan_id,
        algorithm=finding.algorithm,
        api=finding.api,
        operation=finding.operation,
        role=finding.role.value,
        confidence=finding.confidence.value,
        review_path=review_path,
        is_migration_candidate=is_candidate,
        priority=finding.priority.value,
        priority_score=finding.priority_score,
        file_path=finding.file_path,
        start_line=finding.start_line,
        end_line=finding.end_line,
        review_status=review.status.value if review is not None else None,
    )


def review_queue_item_dto(review: ReviewItem, finding: Finding) -> ApiReviewQueueItemDto:
    review_path, _, _ = _migration_for(finding)
    return ApiReviewQueueItemDto(
        review_id=review.id,
        finding_id=finding.id,
        scan_id=finding.scan_id,
        algorithm=finding.algorithm,
        api=finding.api,
        role=finding.role.value,
        review_path=review_path,
        priority=finding.priority.value,
        priority_score=finding.priority_score,
        status=review.status.value,
        assigned_to=review.assigned_to,
        note=review.note,
        reasons=list(finding.priority_reasons or []),
        file_path=finding.file_path,
        start_line=finding.start_line,
        updated_at=_iso(review.updated_at),
    )
