"""Repository and Scan persistence, constraints and version stamping."""

from datetime import datetime

import pytest
from sqlalchemy.exc import IntegrityError, StatementError
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.models import Repository, Scan, ScanJob
from app.db.models.enums import ScanJobStatus, ScanStatus, SourceState


def test_repository_is_created_with_an_id_and_timestamps(session: Session) -> None:
    repository = Repository(
        provider="github",
        owner="pyca",
        name="cryptography",
        canonical_url="https://github.com/pyca/cryptography",
    )
    session.add(repository)
    session.commit()

    assert len(repository.id) == 36
    assert isinstance(repository.created_at, datetime)
    assert isinstance(repository.updated_at, datetime)


def test_repository_identity_is_unique(session: Session, repository: Repository) -> None:
    duplicate = Repository(
        provider=repository.provider,
        owner=repository.owner,
        name=repository.name,
        canonical_url="https://github.com/pyca/cryptography.git",
    )
    session.add(duplicate)

    with pytest.raises(IntegrityError):
        session.commit()


def test_same_name_under_a_different_owner_is_allowed(
    session: Session, repository: Repository
) -> None:
    other = Repository(
        provider="github",
        owner="other",
        name=repository.name,
        canonical_url="https://github.com/other/cryptography",
    )
    session.add(other)
    session.commit()

    assert other.id != repository.id


def test_scan_defaults_come_from_configuration(session: Session, repository: Repository) -> None:
    scan = Scan(repository_id=repository.id, commit_sha="b" * 40)
    session.add(scan)
    session.commit()

    settings = get_settings()
    assert scan.parser_version == settings.parser_version
    assert scan.ruleset_version == settings.ruleset_version
    assert scan.pqc_ruleset_version == settings.pqc_ruleset_version
    assert scan.status is ScanStatus.QUEUED
    assert scan.source_state is SourceState.UNAVAILABLE
    assert scan.file_count == 0
    assert scan.analyzed_file_count == 0
    assert scan.skipped_file_count == 0
    assert scan.finding_count == 0
    assert isinstance(scan.created_at, datetime)


def test_scan_base_commit_sha_is_nullable(scan: Scan) -> None:
    assert scan.base_commit_sha is None


def test_scan_base_commit_sha_can_be_set(session: Session, scan: Scan) -> None:
    scan.base_commit_sha = "c" * 40
    session.commit()

    assert session.get(Scan, scan.id).base_commit_sha == "c" * 40


def test_scan_optional_columns_default_to_null(scan: Scan) -> None:
    assert scan.started_at is None
    assert scan.completed_at is None
    assert scan.error_code is None
    assert scan.error_message is None


@pytest.mark.parametrize("status", list(ScanStatus))
def test_every_scan_status_round_trips(session: Session, scan: Scan, status: ScanStatus) -> None:
    scan.status = status
    session.commit()
    session.expire_all()

    assert session.get(Scan, scan.id).status is status


@pytest.mark.parametrize("state", list(SourceState))
def test_every_source_state_round_trips(
    session: Session, scan: Scan, state: SourceState
) -> None:
    scan.source_state = state
    session.commit()
    session.expire_all()

    assert session.get(Scan, scan.id).source_state is state


def test_scan_status_rejects_an_arbitrary_string(session: Session, scan: Scan) -> None:
    scan.status = "ALMOST_DONE"

    with pytest.raises(StatementError):
        session.commit()


def test_source_state_rejects_an_arbitrary_string(session: Session, scan: Scan) -> None:
    scan.source_state = "STALE"

    with pytest.raises(StatementError):
        session.commit()


def test_scan_job_status_rejects_an_arbitrary_string(session: Session, scan: Scan) -> None:
    session.add(ScanJob(scan_id=scan.id, status="PARKED"))

    with pytest.raises(StatementError):
        session.commit()


def test_scan_job_defaults(session: Session, scan: Scan) -> None:
    job = ScanJob(scan_id=scan.id)
    session.add(job)
    session.commit()

    assert job.status is ScanJobStatus.QUEUED
    assert job.attempt_count == 0
    assert job.locked_at is None
    assert job.started_at is None
    assert job.completed_at is None
    assert job.last_error is None
