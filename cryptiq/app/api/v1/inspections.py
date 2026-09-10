"""Inspection endpoints: submit a scan, read its state, read its findings."""

from __future__ import annotations

from fastapi import APIRouter, status

from app.dependencies import DbSession
from app.schemas.api import (
    ApiFindingSummaryDto,
    ApiInspectionDto,
    ApiListEnvelope,
    CreateInspectionRequest,
)
from app.services import scans
from app.services.serialize import (
    finding_summary_dto,
    inspection_dto,
    severity_breakdown,
)

router = APIRouter(prefix="/inspections", tags=["inspections"])


def _with_severity(session: DbSession, scan_rows: list) -> list[ApiInspectionDto]:
    severities = scans.severity_by_scan(session, [scan.id for scan in scan_rows])
    return [
        inspection_dto(
            scan,
            scan.repository,
            severity=severity_breakdown(severities.get(scan.id, {})),
        )
        for scan in scan_rows
    ]


@router.get("", response_model=ApiListEnvelope[ApiInspectionDto])
def list_inspections(session: DbSession) -> ApiListEnvelope[ApiInspectionDto]:
    rows = scans.list_scans(session)
    items = _with_severity(session, rows)
    return ApiListEnvelope(items=items, total=len(items))


@router.post(
    "",
    response_model=ApiInspectionDto,
    status_code=status.HTTP_201_CREATED,
)
def create_inspection(
    body: CreateInspectionRequest, session: DbSession
) -> ApiInspectionDto:
    scan = scans.create_inspection(session, body.repository_url, body.commit_sha)
    severities = scans.severity_by_scan(session, [scan.id])
    return inspection_dto(
        scan,
        scan.repository,
        severity=severity_breakdown(severities.get(scan.id, {})),
    )


@router.get("/{inspection_id}", response_model=ApiInspectionDto)
def get_inspection(inspection_id: str, session: DbSession) -> ApiInspectionDto:
    scan = scans.get_scan(session, inspection_id)
    severities = scans.severity_by_scan(session, [scan.id])
    return inspection_dto(
        scan,
        scan.repository,
        severity=severity_breakdown(severities.get(scan.id, {})),
    )


@router.get(
    "/{inspection_id}/findings",
    response_model=ApiListEnvelope[ApiFindingSummaryDto],
)
def list_inspection_findings(
    inspection_id: str, session: DbSession
) -> ApiListEnvelope[ApiFindingSummaryDto]:
    findings = scans.list_findings(session, inspection_id)
    items = [finding_summary_dto(finding) for finding in findings]
    return ApiListEnvelope(items=items, total=len(items))
