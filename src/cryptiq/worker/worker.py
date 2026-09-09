"""Database-backed asynchronous scan worker for Cryptiq."""

from __future__ import annotations

import logging
import time
import uuid
from typing import Optional

from cryptiq.core.enums import JobStatus
from cryptiq.core.models import ScanJob
from cryptiq.storage.repositories import JobRepository
from cryptiq.worker.job import JobStateMachine
from cryptiq.worker.service import ScanService

logger = logging.getLogger("cryptiq.worker")


class ScanWorker:
    """Processes scan jobs from the database queue without Redis, Celery, or Kafka.

    Enforces transactional job claiming, bounded retries, state machine validity,
    safe sanitized logging, and complete exception isolation.
    """

    def __init__(
        self,
        job_repo: JobRepository,
        scan_service: ScanService,
        worker_id: Optional[str] = None,
        lock_timeout_seconds: int = 300,
        poll_interval: float = 1.0,
    ):
        self.job_repo = job_repo
        self.scan_service = scan_service
        self.worker_id = worker_id or f"worker-{uuid.uuid4().hex[:8]}"
        self.lock_timeout_seconds = lock_timeout_seconds
        self.poll_interval = poll_interval
        self._stopped = False

    def claim_job(self) -> Optional[ScanJob]:
        """Claim the next claimable job using atomic database locking."""
        return self.job_repo.claim_next_job(
            worker_id=self.worker_id,
            lock_timeout_seconds=self.lock_timeout_seconds,
        )

    def process_next_job(self) -> bool:
        """Claim and process a single job from the queue.

        Returns:
            True if a job was claimed and executed, False if no jobs were available.
        """
        job = self.claim_job()
        if not job:
            return False

        start_time = time.time()
        logger.info(
            "Worker claimed job",
            extra={
                "worker_id": self.worker_id,
                "job_id": job.id,
                "scan_id": job.scan_id,
                "attempt_count": job.attempt_count,
            },
        )

        try:
            # Execute scan orchestration
            scan = self.scan_service.execute(job.scan_id, job_repo=self.job_repo)
            self.job_repo.mark_completed(job.id)

            duration = round((time.time() - start_time) * 1000, 2)
            logger.info(
                "Job completed successfully",
                extra={
                    "worker_id": self.worker_id,
                    "job_id": job.id,
                    "scan_id": job.scan_id,
                    "duration_ms": duration,
                    "finding_count": scan.finding_count,
                    "status": JobStatus.COMPLETED.value,
                },
            )
            return True

        except Exception as exc:
            # Exception isolation: failure on this job does not crash the worker loop
            duration = round((time.time() - start_time) * 1000, 2)
            err_msg = str(exc)

            # Sanitize error message to prevent leaking secrets in logs
            for secret in ["key", "token", "auth", "secret", "password"]:
                if secret in err_msg.lower():
                    err_msg = "Internal execution failure"
                    break

            logger.error(
                "Job execution failed",
                extra={
                    "worker_id": self.worker_id,
                    "job_id": job.id,
                    "scan_id": job.scan_id,
                    "attempt_count": job.attempt_count,
                    "duration_ms": duration,
                    "error": err_msg,
                },
            )

            # Determine retry vs permanent failure
            should_retry = JobStateMachine.should_retry(job)
            if should_retry:
                logger.info(
                    "Re-queuing job for retry",
                    extra={
                        "job_id": job.id,
                        "attempt": job.attempt_count,
                        "max_attempts": job.max_attempts,
                    },
                )
                self.job_repo.mark_failed(job.id, error=err_msg, retry=True)
            else:
                logger.warning(
                    "Job reached max retry attempts; permanently failing",
                    extra={"job_id": job.id, "attempt": job.attempt_count},
                )
                self.job_repo.mark_failed(job.id, error=err_msg, retry=False)
                self.scan_service.fail(job.scan_id, exc)

            return True

    def run_loop(self, max_iterations: Optional[int] = None) -> None:
        """Main worker execution loop."""
        iterations = 0
        while not self._stopped:
            processed = self.process_next_job()
            iterations += 1

            if max_iterations is not None and iterations >= max_iterations:
                break

            if not processed:
                time.sleep(self.poll_interval)

    def stop(self) -> None:
        """Signal the worker loop to stop gracefully."""
        self._stopped = True
