"""Project endpoints: repositories Cryptiq has inspected, and their history."""

from __future__ import annotations

from fastapi import APIRouter

from app.dependencies import DbSession
from app.schemas.api import ApiInspectionDto, ApiListEnvelope, ApiRepositoryDto
from app.services import scans
from app.services.serialize import (
    inspection_dto,
    repository_dto,
    severity_breakdown,
)

router = APIRouter(prefix="/projects", tags=["projects"])


@router.get("", response_model=ApiListEnvelope[ApiRepositoryDto])
def list_projects(session: DbSession) -> ApiListEnvelope[ApiRepositoryDto]:
    repositories = scans.list_repositories(session)
    latest = scans.latest_scan_by_repository(session)
    severities = scans.severity_by_scan(session, [s.id for s in latest.values()])
    items = [
        repository_dto(
            repository,
            latest=latest.get(repository.id),
            findings_count=(
                latest[repository.id].finding_count
                if repository.id in latest
                else None
            ),
        )
        for repository in repositories
    ]
    _ = severities  # reserved for a future per-project severity summary
    return ApiListEnvelope(items=items, total=len(items))


@router.get("/{project_id}", response_model=ApiRepositoryDto)
def get_project(project_id: str, session: DbSession) -> ApiRepositoryDto:
    repository = scans.get_repository(session, project_id)
    latest = scans.list_scans(session, repository_id=project_id)
    newest = latest[0] if latest else None
    return repository_dto(
        repository,
        latest=newest,
        findings_count=newest.finding_count if newest is not None else None,
    )


@router.get(
    "/{project_id}/inspections",
    response_model=ApiListEnvelope[ApiInspectionDto],
)
def list_project_inspections(
    project_id: str, session: DbSession
) -> ApiListEnvelope[ApiInspectionDto]:
    scans.get_repository(session, project_id)
    rows = scans.list_scans(session, repository_id=project_id)
    severities = scans.severity_by_scan(session, [row.id for row in rows])
    items = [
        inspection_dto(
            row,
            row.repository,
            severity=severity_breakdown(severities.get(row.id, {})),
        )
        for row in rows
    ]
    return ApiListEnvelope(items=items, total=len(items))
