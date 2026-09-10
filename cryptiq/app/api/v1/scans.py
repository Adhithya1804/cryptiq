"""Scan endpoints — the canonical names the frontend calls.

``/api/v1/scans`` is the same entity as ``/api/v1/inspections`` (a scan of one
repository at one exact commit); both are kept so neither the frontend nor the
existing tests have to move at once. The scan routes add the two things the
inspection routes never grew: a distinct ``202``/``200`` on submit so the
client can tell "queued" from "served from cache", and a real paginated,
server-filtered findings page.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query, Response, status

from app.dependencies import DbSession
from app.schemas.api import (
    ApiFindingSummaryDto,
    ApiInspectionDto,
    ApiPageEnvelope,
    CreateInspectionRequest,
)
from app.services import scans
from app.services.serialize import (
    finding_summary_dto,
    inspection_dto,
    severity_breakdown,
)

router = APIRouter(prefix="/scans", tags=["scans"])


def _inspection_dto(session: DbSession, scan, *, cached: bool = False) -> ApiInspectionDto:
    severities = scans.severity_by_scan(session, [scan.id])
    dto = inspection_dto(
        scan,
        scan.repository,
        severity=severity_breakdown(severities.get(scan.id, {})),
    )
    dto.cached = cached
    return dto


@router.post("", response_model=ApiInspectionDto, status_code=status.HTTP_202_ACCEPTED)
def create_scan(
    body: CreateInspectionRequest, session: DbSession, response: Response
) -> ApiInspectionDto:
    """Queue a scan (``202``), or return an identical completed one (``200``).

    The engine is a pure function of the seven-part scan identity, so a repeat
    request for a commit already analysed is answered from the stored findings
    with ``cached: true`` and no new work.
    """
    scan, cached = scans.create_scan(session, body.repository_url, body.commit_sha)
    if cached:
        response.status_code = status.HTTP_200_OK
    return _inspection_dto(session, scan, cached=cached)


@router.get("/{scan_id}", response_model=ApiInspectionDto)
def get_scan(scan_id: str, session: DbSession) -> ApiInspectionDto:
    scan = scans.get_scan(session, scan_id)
    return _inspection_dto(session, scan)


@router.get(
    "/{scan_id}/findings",
    response_model=ApiPageEnvelope[ApiFindingSummaryDto],
)
def list_scan_findings(
    scan_id: str,
    session: DbSession,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=scans.MAX_PAGE_SIZE)] = scans.DEFAULT_PAGE_SIZE,
    priority: str | None = None,
    algorithm: str | None = None,
    role: str | None = None,
    status: str | None = None,
    confidence: str | None = None,
) -> ApiPageEnvelope[ApiFindingSummaryDto]:
    rows, total = scans.list_findings_page(
        session,
        scan_id,
        page=page,
        page_size=page_size,
        priority=priority,
        algorithm=algorithm,
        role=role,
        confidence=confidence,
        review_status=status,
    )
    pages = max((total + page_size - 1) // page_size, 1)
    return ApiPageEnvelope(
        items=[finding_summary_dto(row) for row in rows],
        total=total,
        page=page,
        page_size=page_size,
        pages=pages,
    )
