"""Finding endpoints: full detail, AI explanation, and review disposition."""

from __future__ import annotations

from fastapi import APIRouter, Query

from app.dependencies import DbSession
from app.engine.context.models import DomainProfile
from app.schemas.api import (
    ApiContextualAssessmentDto,
    ApiExplanationDto,
    ApiFindingDto,
    ApiReviewBlock,
    CreateMigrationAssessmentRequest,
    SubmitReviewRequest,
)
from app.services import scans
from app.services.explanations import generate_explanation
from app.services.migration_assessments import generate_migration_assessment
from app.services.reviews import record_disposition
from app.services.serialize import finding_dto, review_block

router = APIRouter(prefix="/findings", tags=["findings"])


@router.get("/{finding_id}", response_model=ApiFindingDto)
def get_finding(finding_id: str, session: DbSession) -> ApiFindingDto:
    finding = scans.get_finding(session, finding_id)
    scan = scans.get_scan(session, finding.scan_id)
    return finding_dto(finding, scan, scan.repository)


@router.post("/{finding_id}/explanation", response_model=ApiExplanationDto)
def create_finding_explanation(
    finding_id: str, session: DbSession
) -> ApiExplanationDto:
    """Generate (or return the cached) AI explanation for an existing finding.

    The finding id is the whole input. The route takes no request body, so a
    browser cannot supply prompt text or source text -- any JSON sent is
    ignored by FastAPI. Failure is controlled (``AI_EXPLANATION_UNAVAILABLE``)
    and never affects the finding itself.
    """
    finding = scans.get_finding(session, finding_id)
    scan = scans.get_scan(session, finding.scan_id)
    return generate_explanation(session, finding, scan)


@router.get("/{finding_id}/explanation", response_model=ApiExplanationDto)
def get_finding_explanation(finding_id: str, session: DbSession) -> ApiExplanationDto:
    """Backward-compatible alias for the POST route; same generate-or-cache."""
    finding = scans.get_finding(session, finding_id)
    scan = scans.get_scan(session, finding.scan_id)
    return generate_explanation(session, finding, scan)


@router.post("/{finding_id}/migration-assessment", response_model=ApiContextualAssessmentDto)
def create_finding_migration_assessment(
    finding_id: str,
    session: DbSession,
    body: CreateMigrationAssessmentRequest | None = None,
) -> ApiContextualAssessmentDto:
    """Generate (or return cached) context-aware migration assessment for a finding."""
    finding = scans.get_finding(session, finding_id)
    scan = scans.get_scan(session, finding.scan_id)
    profile = (
        DomainProfile.from_dict(body.domain_profile.model_dump())
        if body and body.domain_profile
        else DomainProfile()
    )
    return generate_migration_assessment(session, finding, scan, domain_profile=profile)


@router.get("/{finding_id}/migration-assessment", response_model=ApiContextualAssessmentDto)
def get_finding_migration_assessment(
    finding_id: str,
    session: DbSession,
    domain: str | None = Query(default=None, max_length=64),
) -> ApiContextualAssessmentDto:
    """Retrieve or generate contextual migration assessment with optional domain filter."""
    finding = scans.get_finding(session, finding_id)
    scan = scans.get_scan(session, finding.scan_id)
    profile = DomainProfile.from_dict({"domain": domain}) if domain else DomainProfile()
    return generate_migration_assessment(session, finding, scan, domain_profile=profile)


@router.post("/{finding_id}/review", response_model=ApiReviewBlock)
def submit_finding_review(
    finding_id: str, body: SubmitReviewRequest, session: DbSession
) -> ApiReviewBlock:
    review = record_disposition(session, finding_id, body.status, body.note)
    return review_block(review)
