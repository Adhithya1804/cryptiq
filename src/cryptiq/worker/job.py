"""ScanJob state machine and transition enforcement."""

from __future__ import annotations

from typing import Set, Tuple

from cryptiq.core.enums import JobStatus
from cryptiq.core.models import ScanJob


class InvalidStateTransitionError(ValueError):
    """Raised when an illegal job state transition is attempted."""


# Explicit set of legal state transitions: (source_status, target_status)
LEGAL_TRANSITIONS: Set[Tuple[JobStatus, JobStatus]] = {
    (JobStatus.QUEUED, JobStatus.RUNNING),
    (JobStatus.RUNNING, JobStatus.COMPLETED),
    (JobStatus.RUNNING, JobStatus.FAILED),
    (JobStatus.RUNNING, JobStatus.QUEUED),  # Retry
    (JobStatus.QUEUED, JobStatus.CANCELLED),
    (JobStatus.RUNNING, JobStatus.CANCELLED),
}


class JobStateMachine:
    """Validates and applies state transitions for ScanJob."""

    @staticmethod
    def validate_transition(current: JobStatus, target: JobStatus) -> None:
        """Validate whether transition from current to target is allowed."""
        if (current, target) not in LEGAL_TRANSITIONS:
            raise InvalidStateTransitionError(
                f"Illegal state transition from {current.value} to {target.value}"
            )

    @staticmethod
    def should_retry(job: ScanJob) -> bool:
        """Determine if a failed job attempt should be retried based on max_attempts."""
        return job.attempt_count < job.max_attempts
