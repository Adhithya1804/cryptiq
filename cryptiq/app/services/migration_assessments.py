"""Orchestration and persistence for contextual migration assessments.

Manages caching, audit events, fallback handling, and DTO conversion.
"""

from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.audit_event import AuditEvent
from app.db.models.enums import AuditEventType
from app.db.models.finding import Finding
from app.db.models.migration_assessment import MigrationAssessmentRecord
from app.db.models.scan import Scan
from app.engine.context.models import (
    AssessmentConfidence,
    AssessmentDecision,
    ContextualAssessment,
    ContextualRole,
    DomainProfile,
)
from app.schemas.api import ApiContextualAssessmentDto
from app.services.context_advisor import ContextAdvisorService

logger = logging.getLogger(__name__)

_FAILURE_CODE = "MIGRATION_ASSESSMENT_FAILED"


def _record_audit(
    session: Session, finding: Finding, event_type: AuditEventType, **metadata: object
) -> None:
    session.add(
        AuditEvent(
            scan_id=finding.scan_id,
            finding_id=finding.id,
            event_type=event_type,
            event_metadata=dict(metadata),
        )
    )


def to_dto(
    assessment: ContextualAssessment,
    *,
    record_id: str | None = None,
    created_at: str | None = None,
) -> ApiContextualAssessmentDto:
    """Convert a ContextualAssessment domain object to an API DTO."""
    return ApiContextualAssessmentDto(
        id=record_id,
        finding_id=assessment.finding_id or "",
        fingerprint=assessment.fingerprint,
        assessment=assessment.assessment.value,
        confidence=assessment.confidence.value,
        contextual_role=assessment.contextual_role.value,
        rationale=assessment.rationale,
        pqc_migration_required=assessment.pqc_migration_required,
        migration_candidate=assessment.migration_candidate,
        alternatives=list(assessment.alternatives),
        engineering_tradeoffs=list(assessment.engineering_tradeoffs),
        required_context=list(assessment.required_context),
        evidence_interpretation=assessment.evidence_interpretation,
        knowledge_sources=[dict(k) for k in assessment.knowledge_sources],
        limitations=list(assessment.limitations),
        domain_profile=assessment.domain_profile.to_dict(),
        generated_by=assessment.generated_by,
        model=assessment.model,
        prompt_version=assessment.prompt_version,
        cached=assessment.cached,
        created_at=created_at,
    )


def _cached_assessment(
    session: Session,
    finding: Finding,
    profile: DomainProfile,
    service: ContextAdvisorService,
) -> MigrationAssessmentRecord | None:
    model_name = service.model if service.is_configured else None
    return session.scalars(
        select(MigrationAssessmentRecord)
        .where(
            MigrationAssessmentRecord.finding_id == finding.id,
            MigrationAssessmentRecord.finding_fingerprint == finding.fingerprint,
            MigrationAssessmentRecord.domain_profile_hash == profile.profile_hash(),
            MigrationAssessmentRecord.knowledge_version == service.knowledge_version,
            MigrationAssessmentRecord.prompt_version == service.prompt_version,
            MigrationAssessmentRecord.model == model_name,
            MigrationAssessmentRecord.status == "COMPLETED",
        )
        .order_by(MigrationAssessmentRecord.created_at.desc())
    ).first()


def record_to_assessment(
    record: MigrationAssessmentRecord,
    profile: DomainProfile,
) -> ContextualAssessment:
    payload = record.payload or {}
    try:
        decision = AssessmentDecision(record.decision or "REVIEW")
    except ValueError:
        decision = AssessmentDecision.REVIEW

    try:
        conf = AssessmentConfidence(record.confidence or "MEDIUM")
    except ValueError:
        conf = AssessmentConfidence.MEDIUM

    try:
        role = ContextualRole(record.contextual_role or "UNKNOWN")
    except ValueError:
        role = ContextualRole.UNKNOWN

    return ContextualAssessment(
        finding_id=record.finding_id,
        fingerprint=record.finding_fingerprint or "",
        assessment=decision,
        confidence=conf,
        contextual_role=role,
        rationale=payload.get("rationale", ""),
        pqc_migration_required=payload.get("pqc_migration_required", False),
        migration_candidate=payload.get("migration_candidate"),
        alternatives=tuple(payload.get("alternatives", ())),
        engineering_tradeoffs=tuple(payload.get("engineering_tradeoffs", ())),
        required_context=tuple(payload.get("required_context", ())),
        evidence_interpretation=payload.get("evidence_interpretation", ""),
        knowledge_sources=tuple(payload.get("knowledge_sources", ())),
        limitations=tuple(payload.get("limitations", ())),
        domain_profile=profile,
        generated_by=payload.get("generated_by", record.provider),
        model=record.model,
        prompt_version=record.prompt_version,
        cached=True,
    )


def generate_migration_assessment(
    session: Session,
    finding: Finding,
    scan: Scan,
    domain_profile: DomainProfile | None = None,
    *,
    service: ContextAdvisorService | None = None,
) -> ApiContextualAssessmentDto:
    """Generate, cache, and audit a contextual migration assessment for one finding."""
    service = service or ContextAdvisorService()
    profile = domain_profile or DomainProfile()

    # 1. Check cache
    cached = _cached_assessment(session, finding, profile, service)
    if cached is not None:
        assessment = record_to_assessment(cached, profile)
        return to_dto(
            assessment,
            record_id=cached.id,
            created_at=cached.created_at.isoformat() if cached.created_at else None,
        )

    # 2. Record audit start
    _record_audit(
        session,
        finding,
        AuditEventType.MIGRATION_ASSESSMENT_REQUESTED,
        prompt_version=service.prompt_version,
        knowledge_version=service.knowledge_version,
        domain=profile.domain,
        domain_profile_hash=profile.profile_hash(),
        finding_fingerprint=finding.fingerprint,
    )

    model_name = service.model if service.is_configured else None
    record = MigrationAssessmentRecord(
        finding_id=finding.id,
        provider=service.provider if service.is_configured else "heuristic",
        model=model_name,
        prompt_version=service.prompt_version,
        knowledge_version=service.knowledge_version,
        finding_fingerprint=finding.fingerprint,
        domain=profile.domain,
        domain_profile_hash=profile.profile_hash(),
        status="PENDING",
    )
    session.add(record)
    session.flush()

    # 3. Generate assessment
    try:
        assessment = service.assess_finding(finding, scan, profile)
        record.status = "COMPLETED"
        record.decision = assessment.assessment.value
        record.confidence = assessment.confidence.value
        record.contextual_role = assessment.contextual_role.value
        record.payload = assessment.to_dict()

        _record_audit(
            session,
            finding,
            AuditEventType.MIGRATION_ASSESSMENT_COMPLETED,
            decision=assessment.assessment.value,
            contextual_role=assessment.contextual_role.value,
            generated_by=assessment.generated_by,
        )
        session.commit()
        session.refresh(record)

        return to_dto(
            assessment,
            record_id=record.id,
            created_at=record.created_at.isoformat() if record.created_at else None,
        )
    except Exception as exc:
        record.status = "FAILED"
        record.error_code = _FAILURE_CODE
        record.error_message = str(exc)
        session.commit()
        logger.error("Failed to generate migration assessment for %s: %s", finding.id, exc)
        raise
