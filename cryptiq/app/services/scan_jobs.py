"""The rules a scan job's lifecycle must obey.

The worker loop is a later phase. What lives here is the part that must be
right before any loop exists: which transitions are legal, and when a failed
job has run out of attempts. Keeping it apart from the loop means the rules
can be tested without a database or a scheduler.
"""

from app.db.models.enums import ScanJobStatus
from app.db.models.scan_job import ScanJob
from app.errors import CryptiqError

# Every transition a job may make. A job leaves QUEUED only by being claimed,
# and returns to QUEUED only as a retry.
LEGAL_TRANSITIONS: frozenset[tuple[ScanJobStatus, ScanJobStatus]] = frozenset(
    {
        (ScanJobStatus.QUEUED, ScanJobStatus.RUNNING),
        (ScanJobStatus.QUEUED, ScanJobStatus.CANCELLED),
        (ScanJobStatus.RUNNING, ScanJobStatus.COMPLETED),
        (ScanJobStatus.RUNNING, ScanJobStatus.FAILED),
        (ScanJobStatus.RUNNING, ScanJobStatus.QUEUED),
        (ScanJobStatus.RUNNING, ScanJobStatus.CANCELLED),
    }
)

TERMINAL_STATUSES: frozenset[ScanJobStatus] = frozenset(
    {ScanJobStatus.COMPLETED, ScanJobStatus.FAILED, ScanJobStatus.CANCELLED}
)


class InvalidJobTransitionError(CryptiqError):
    """Raised when a job is moved between states in a way the lifecycle forbids."""

    status_code = 409
    code = "INVALID_JOB_TRANSITION"


def assert_transition(current: ScanJobStatus, target: ScanJobStatus) -> None:
    """Raise unless a job may move from one status to the other."""
    if (current, target) not in LEGAL_TRANSITIONS:
        raise InvalidJobTransitionError(
            f"A scan job cannot move from {current.value} to {target.value}."
        )


def should_retry(job: ScanJob) -> bool:
    """Return whether a failed attempt leaves the job any attempts to spend."""
    return job.attempt_count < job.max_attempts


def is_terminal(status: ScanJobStatus) -> bool:
    """Return whether a job in this status will never run again."""
    return status in TERMINAL_STATUSES
