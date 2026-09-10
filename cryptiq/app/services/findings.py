"""Turning engine results into the canonical API representation.

The engine's ``AnalyzedFinding`` is the source of truth. This module only
reshapes it; it never recomputes, re-reads source, or decides anything the
engine did not already establish.
"""

from app.db.models.review_item import ReviewItem
from app.engine.engine import engine_versions
from app.engine.ingestion import RepositoryReference
from app.engine.pipeline import AnalysisResult, AnalyzedFinding
from app.schemas.finding import (
    FindingPage,
    FindingRead,
    FindingSummary,
    ImpactEdgeRead,
    ImpactNodeRead,
    ImpactRead,
    InferenceRead,
    MigrationRead,
    ObservedRead,
    PriorityRead,
    RepositoryRef,
    ReviewQueue,
    ReviewQueueItem,
    ReviewRead,
    SourceLocationRead,
)


def repository_ref(repository: RepositoryReference) -> RepositoryRef:
    """Return the repository identity a client sees."""
    return RepositoryRef(
        provider=repository.provider,
        owner=repository.owner,
        name=repository.name,
        url=repository.canonical_url,
    )


def to_finding(
    finding: AnalyzedFinding,
    *,
    scan_id: str,
    repository: RepositoryReference,
    commit_sha: str,
    review: ReviewItem | None = None,
) -> FindingRead:
    """Return the complete canonical representation of one finding."""
    match = finding.match
    versions = engine_versions()

    return FindingRead(
        id=finding.fingerprint,
        scan_id=scan_id,
        repository=repository_ref(repository),
        commit_sha=commit_sha,
        observed=ObservedRead(
            rule_id=match.rule_id,
            algorithm=match.algorithm,
            primitive=match.primitive,
            library=match.library,
            api=match.api,
            operation=match.operation,
            location=SourceLocationRead(
                file_path=match.file_path,
                start_line=match.location.start_line,
                end_line=match.location.end_line,
                start_column=match.location.start_column,
                end_column=match.location.end_column,
            ),
            source_excerpt=finding.evidence.source_excerpt,
            enclosing_function=match.enclosing_function,
            enclosing_class=match.enclosing_class,
            parser_version=finding.evidence.parser_version,
            ruleset_version=finding.evidence.ruleset_version,
        ),
        inference=InferenceRead(
            role=finding.role.role,
            rationale=finding.role.rationale,
            confidence=match.confidence,
            evidence_basis=match.evidence_basis,
        ),
        migration=MigrationRead(
            review_path=finding.pqc.review_path,
            rationale=finding.pqc.rationale,
            is_migration_candidate=finding.pqc.is_migration_candidate,
            pqc_ruleset_version=versions.pqc_ruleset_version,
        ),
        impact=ImpactRead(
            scope=finding.impact.scope,
            node_count=finding.impact.node_count,
            nodes=[
                ImpactNodeRead(
                    id=node.id,
                    node_type=node.node_type.value,
                    label=node.label,
                    relationship=node.relationship.value if node.relationship else None,
                )
                for node in finding.impact.nodes
            ],
            relationships=[
                ImpactEdgeRead(
                    source_id=edge.source_id,
                    target_id=edge.target_id,
                    relationship=edge.relationship.value,
                )
                for edge in finding.impact.relationships
            ],
        ),
        priority=PriorityRead(
            level=finding.priority.level.value,
            score=finding.priority.score,
            reasons=list(finding.priority.reasons),
        ),
        review=ReviewRead.model_validate(review) if review is not None else None,
    )


def to_summary(
    finding: AnalyzedFinding, *, scan_id: str, review: ReviewItem | None = None
) -> FindingSummary:
    """Return the row representation of one finding."""
    match = finding.match
    return FindingSummary(
        id=finding.fingerprint,
        scan_id=scan_id,
        algorithm=match.algorithm,
        api=match.api,
        operation=match.operation,
        role=finding.role.role,
        confidence=match.confidence,
        review_path=finding.pqc.review_path,
        is_migration_candidate=finding.pqc.is_migration_candidate,
        priority=finding.priority.level.value,
        priority_score=finding.priority.score,
        file_path=match.file_path,
        start_line=match.location.start_line,
        end_line=match.location.end_line,
        review_status=review.status if review is not None else None,
    )


def to_page(result: AnalysisResult, *, scan_id: str) -> FindingPage:
    """Return every finding of a scan, in the engine's deterministic order."""
    return FindingPage(
        scan_id=scan_id,
        total=len(result.findings),
        findings=[to_summary(finding, scan_id=scan_id) for finding in result.findings],
    )


def to_review_queue(
    pairs: list[tuple[AnalyzedFinding, ReviewItem]], *, scan_id: str
) -> ReviewQueue:
    """Return the review queue, highest priority score first.

    Ordering is by score descending, then by the engine's own order, so two
    findings that score the same never swap places between requests.
    """
    ordered = sorted(
        pairs,
        key=lambda pair: (-pair[0].priority.score, pair[0].sort_key),
    )
    return ReviewQueue(
        scan_id=scan_id,
        total=len(ordered),
        items=[
            ReviewQueueItem(
                review_id=review.id,
                finding_id=finding.fingerprint,
                scan_id=scan_id,
                algorithm=finding.match.algorithm,
                api=finding.match.api,
                role=finding.role.role,
                review_path=finding.pqc.review_path,
                priority=finding.priority.level.value,
                priority_score=finding.priority.score,
                status=review.status,
                assigned_to=review.assigned_to,
                note=review.note,
                file_path=finding.match.file_path,
                start_line=finding.match.location.start_line,
                updated_at=review.updated_at,
            )
            for finding, review in ordered
        ],
    )
