"""Domain schemas convert models without exposing SQLAlchemy objects."""

import pytest
from pydantic import ValidationError

from app.db.models import Finding, Repository, Scan, ScanJob
from app.db.models.enums import ScanJobStatus, ScanStatus, SourceState
from app.schemas import RepositoryRead, ScanCreate, ScanJobRead, ScanRead


def test_repository_read_from_model(repository: Repository) -> None:
    schema = RepositoryRead.model_validate(repository)

    assert schema.id == repository.id
    assert schema.provider == "github"
    assert schema.canonical_url == "https://github.com/pyca/cryptography"


def test_scan_read_from_model(scan: Scan, finding: Finding) -> None:
    schema = ScanRead.model_validate(scan)

    assert schema.id == scan.id
    assert schema.status is ScanStatus.QUEUED
    assert schema.source_state is SourceState.UNAVAILABLE
    assert schema.parser_version == scan.parser_version
    assert schema.base_commit_sha is None


def test_scan_job_read_from_model(session, scan: Scan) -> None:
    job = ScanJob(scan_id=scan.id)
    session.add(job)
    session.commit()

    schema = ScanJobRead.model_validate(job)

    assert schema.scan_id == scan.id
    assert schema.status is ScanJobStatus.QUEUED


def test_scan_create_rejects_a_short_commit_sha() -> None:
    with pytest.raises(ValidationError):
        ScanCreate(repository_id="r", commit_sha="abc")


def test_scan_create_accepts_an_optional_base_commit() -> None:
    request = ScanCreate(repository_id="r", commit_sha="a" * 40)

    assert request.base_commit_sha is None
