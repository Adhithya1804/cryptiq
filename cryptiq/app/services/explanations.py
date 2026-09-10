"""Orchestration for AI explanations of findings.

An explanation is a subordinate layer: it restates, in prose, what the
deterministic engine already established, for a reviewer who wants orientation.
It never establishes a fact and the finding is fully usable without it.

Responsibilities here (the Gemini call itself lives in
:mod:`app.services.gemini`):

* refuse when AI is not configured -- controlled, never fatal;
* serve a cached explanation whenever one exists for the same
  ``finding fingerprint + prompt version + model``, with no model call;
* on a miss, build the bounded input, call the isolated service, persist the
  validated payload, and record audit events;
* on any AI failure, persist a ``FAILED`` row, leave the finding untouched, and
  raise one controlled error (``AI_EXPLANATION_UNAVAILABLE``).
"""

from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.audit_event import AuditEvent
from app.db.models.enums import AuditEventType, ExplanationStatus
from app.db.models.explanation import Explanation
from app.db.models.finding import Finding
from app.db.models.scan import Scan
from app.errors import CryptiqError
from app.integrations.gemini import GeminiError
from app.schemas.api import ApiExplanationDto
from app.services.gemini import GeminiExplanationService, build_input

logger = logging.getLogger(__name__)

_FAILURE_CODE = "AI_EXPLANATION_UNAVAILABLE"


class ExplanationUnavailableError(CryptiqError):
    """The single controlled failure for the AI explanation layer.

    Covers "not configured", provider/transport failure, timeout, and
    malformed model output. The deterministic finding is unaffected.
    """

    status_code = 503
    code = _FAILURE_CODE

    def __init__(
        self, message: str = "AI explanation is temporarily unavailable."
    ) -> None:
        super().__init__(message)


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


def _to_dto(
    finding_id: str, explanation: Explanation, *, cached: bool
) -> ApiExplanationDto:
    payload = explanation.payload or {}
    return ApiExplanationDto(
        finding_id=finding_id,
        provider=explanation.provider,
        model=explanation.model,
        prompt_version=explanation.prompt_version,
        summary=payload.get("summary") or explanation.summary or "",
        why_it_matters=payload.get("why_it_matters", ""),
        evidence_explanation=payload.get("evidence_explanation", ""),
        migration_explanation=payload.get("migration_explanation", ""),
        impact_explanation=payload.get("impact_explanation", ""),
        limitations=list(payload.get("limitations", [])),
        cached=cached,
        generated_at=explanation.created_at.isoformat()
        if explanation.created_at is not None
        else None,
    )


def _cached_explanation(
    session: Session, finding: Finding, service: GeminiExplanationService
) -> Explanation | None:
    return session.scalars(
        select(Explanation)
        .where(
            Explanation.finding_id == finding.id,
            Explanation.prompt_version == service.prompt_version,
            Explanation.model == service.model,
            Explanation.finding_fingerprint == finding.fingerprint,
            Explanation.status == ExplanationStatus.COMPLETED,
        )
        .order_by(Explanation.created_at.desc())
    ).first()


def generate_explanation(
    session: Session,
    finding: Finding,
    scan: Scan,
    *,
    service: GeminiExplanationService | None = None,
) -> ApiExplanationDto:
    """Return an explanation for a finding, generating and caching it once."""
    service = service or GeminiExplanationService()

    if not service.is_configured:
        # Nothing is persisted and nothing is billed; the finding stands.
        raise ExplanationUnavailableError("AI explanations are not configured.")

    cached = _cached_explanation(session, finding, service)
    if cached is not None:
        return _to_dto(finding.id, cached, cached=True)

    _record_audit(
        session,
        finding,
        AuditEventType.EXPLANATION_REQUESTED,
        prompt_version=service.prompt_version,
        model=service.model,
        finding_fingerprint=finding.fingerprint,
    )

    record = Explanation(
        finding_id=finding.id,
        provider=service.provider,
        model=service.model,
        prompt_version=service.prompt_version,
        finding_fingerprint=finding.fingerprint,
        status=ExplanationStatus.PENDING,
    )
    session.add(record)
    session.flush()

    logger.info(
        "gemini explanation requested for finding %s (model=%s)",
        finding.id,
        service.model,
    )
    try:
        payload = service.explain(build_input(finding, scan))
    except GeminiError as exc:
        record.status = ExplanationStatus.FAILED
        record.error_code = _FAILURE_CODE
        record.error_message = str(exc)
        session.commit()
        logger.warning("explanation for finding %s unavailable: %s", finding.id, exc)
        raise ExplanationUnavailableError() from exc
    logger.info("gemini explanation completed for finding %s", finding.id)

    record.status = ExplanationStatus.COMPLETED
    record.payload = payload.model_dump()
    # Mirror the two most-read fields into their own columns for cheap querying;
    # the canonical copy is ``payload``.
    record.summary = payload.summary
    record.why_it_matters = payload.why_it_matters
    _record_audit(
        session,
        finding,
        AuditEventType.EXPLANATION_COMPLETED,
        prompt_version=service.prompt_version,
        model=service.model,
    )
    session.commit()
    session.refresh(record)
    return _to_dto(finding.id, record, cached=False)
