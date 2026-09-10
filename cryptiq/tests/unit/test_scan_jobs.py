"""The scan job lifecycle rules."""

import pytest

from app.db.models import ScanJob
from app.db.models.enums import ScanJobStatus
from app.db.models.scan_job import DEFAULT_MAX_ATTEMPTS
from app.services import InvalidJobTransitionError, assert_transition, is_terminal, should_retry


@pytest.mark.parametrize(
    ("current", "target"),
    [
        (ScanJobStatus.QUEUED, ScanJobStatus.RUNNING),
        (ScanJobStatus.QUEUED, ScanJobStatus.CANCELLED),
        (ScanJobStatus.RUNNING, ScanJobStatus.COMPLETED),
        (ScanJobStatus.RUNNING, ScanJobStatus.FAILED),
        (ScanJobStatus.RUNNING, ScanJobStatus.QUEUED),
        (ScanJobStatus.RUNNING, ScanJobStatus.CANCELLED),
    ],
)
def test_legal_transitions_are_allowed(current, target) -> None:
    assert_transition(current, target)


@pytest.mark.parametrize(
    ("current", "target"),
    [
        (ScanJobStatus.QUEUED, ScanJobStatus.COMPLETED),
        (ScanJobStatus.QUEUED, ScanJobStatus.FAILED),
        (ScanJobStatus.COMPLETED, ScanJobStatus.RUNNING),
        (ScanJobStatus.FAILED, ScanJobStatus.RUNNING),
        (ScanJobStatus.CANCELLED, ScanJobStatus.QUEUED),
        (ScanJobStatus.RUNNING, ScanJobStatus.RUNNING),
    ],
)
def test_illegal_transitions_are_refused(current, target) -> None:
    with pytest.raises(InvalidJobTransitionError) as error:
        assert_transition(current, target)

    assert error.value.code == "INVALID_JOB_TRANSITION"
    assert error.value.status_code == 409


def test_a_job_may_retry_until_its_ceiling() -> None:
    job = ScanJob(scan_id="s", attempt_count=0, max_attempts=3)

    assert should_retry(job)

    job.attempt_count = 2
    assert should_retry(job)

    job.attempt_count = 3
    assert not should_retry(job)


def test_terminal_statuses_never_run_again() -> None:
    assert is_terminal(ScanJobStatus.COMPLETED)
    assert is_terminal(ScanJobStatus.FAILED)
    assert is_terminal(ScanJobStatus.CANCELLED)
    assert not is_terminal(ScanJobStatus.QUEUED)
    assert not is_terminal(ScanJobStatus.RUNNING)


def test_a_new_job_carries_the_default_retry_ceiling(session, scan) -> None:
    job = ScanJob(scan_id=scan.id)
    session.add(job)
    session.commit()

    assert job.max_attempts == DEFAULT_MAX_ATTEMPTS
    assert job.locked_by is None


def test_a_claimed_job_records_its_holder(session, scan) -> None:
    from datetime import UTC, datetime

    job = ScanJob(scan_id=scan.id)
    session.add(job)
    session.commit()

    job.status = ScanJobStatus.RUNNING
    job.locked_at = datetime.now(UTC)
    job.locked_by = "worker-1"
    job.attempt_count += 1
    session.commit()

    stored = session.get(ScanJob, job.id)
    assert stored.locked_by == "worker-1"
    assert stored.attempt_count == 1
