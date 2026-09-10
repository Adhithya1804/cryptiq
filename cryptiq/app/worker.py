"""The scan worker: claim a queued job, run the engine, persist the result.

One in-process async loop, started with the application. It is deliberately
small -- claim, run, record -- because the lifecycle rules it must obey already
live in :mod:`app.services.scan_jobs` and the analysis itself is the engine's.

The engine is synchronous and CPU-bound, so it runs in a worker thread; the
ingestion download is async and runs on the loop.
"""

from __future__ import annotations

import asyncio
import logging
import os
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.database import SessionLocal
from app.db.models.enums import ScanJobStatus, ScanStatus, SourceState
from app.db.models.scan import Scan
from app.db.models.scan_job import ScanJob
from app.engine.ingestion import RepositoryReference, ingest_commit
from app.engine.pipeline import analyze_snapshot
from app.errors import IngestionError
from app.integrations.github import GitHubSourceProvider
from app.services.persistence import persist_analysis
from app.services.scan_jobs import assert_transition, should_retry

logger = logging.getLogger(__name__)

POLL_INTERVAL_SECONDS = 1.0
_WORKER_ID = f"worker-{os.getpid()}"


def _now() -> datetime:
    return datetime.now(UTC)


def _claim_next_job(session: Session) -> ScanJob | None:
    """Claim the oldest queued job, or return None if the queue is empty.

    On PostgreSQL the row is locked with ``FOR UPDATE SKIP LOCKED`` so more
    than one worker can run safely; SQLite has no such clause and runs a
    single in-process worker, where a plain select is enough.
    """
    statement = (
        select(ScanJob)
        .where(ScanJob.status == ScanJobStatus.QUEUED)
        .order_by(ScanJob.created_at, ScanJob.id)
        .limit(1)
    )
    if session.bind is not None and session.bind.dialect.name == "postgresql":
        statement = statement.with_for_update(skip_locked=True)

    job = session.scalars(statement).first()
    if job is None:
        return None

    assert_transition(job.status, ScanJobStatus.RUNNING)
    job.status = ScanJobStatus.RUNNING
    job.attempt_count += 1
    job.locked_at = _now()
    job.locked_by = _WORKER_ID
    job.started_at = _now()

    scan = session.get(Scan, job.scan_id)
    if scan is not None and scan.status == ScanStatus.QUEUED:
        scan.status = ScanStatus.RUNNING
        scan.started_at = _now()
    session.commit()
    return job


def _fail(session: Session, job: ScanJob, code: str, message: str) -> None:
    scan = session.get(Scan, job.scan_id)
    retry = should_retry(job)
    job.completed_at = _now()
    job.last_error = f"{code}: {message}"
    if retry:
        assert_transition(job.status, ScanJobStatus.QUEUED)
        job.status = ScanJobStatus.QUEUED
        job.locked_at = None
        job.locked_by = None
        if scan is not None:
            scan.status = ScanStatus.QUEUED
    else:
        assert_transition(job.status, ScanJobStatus.FAILED)
        job.status = ScanJobStatus.FAILED
        if scan is not None:
            scan.status = ScanStatus.FAILED
            scan.completed_at = _now()
            scan.error_code = code
            scan.error_message = message
    session.commit()
    logger.warning("scan %s failed (%s): %s (retry=%s)", job.scan_id, code, message, retry)


async def _execute(session: Session, job: ScanJob) -> None:
    scan = session.get(Scan, job.scan_id)
    if scan is None:  # pragma: no cover - the FK makes this unreachable
        raise RuntimeError(f"job {job.id} references a missing scan")
    repository = scan.repository
    reference = RepositoryReference(
        provider=repository.provider,
        owner=repository.owner,
        name=repository.name,
        canonical_url=repository.canonical_url,
    )

    provider = GitHubSourceProvider()
    async with ingest_commit(provider, reference, scan.commit_sha) as ingestion:
        result = await asyncio.to_thread(
            analyze_snapshot, ingestion, ingestion.snapshot.root_path
        )

    scan.commit_sha = result.commit_sha
    scan.source_state = SourceState.LIVE
    persist_analysis(session, scan, result)

    assert_transition(job.status, ScanJobStatus.COMPLETED)
    job.status = ScanJobStatus.COMPLETED
    job.completed_at = _now()
    scan.status = ScanStatus.COMPLETED
    scan.completed_at = _now()
    session.commit()
    logger.info("scan %s completed: %d findings", scan.id, scan.finding_count)


async def run_next_job() -> bool:
    """Claim and run one job. Return True if a job was processed."""
    session = SessionLocal()
    try:
        job = _claim_next_job(session)
        if job is None:
            return False
        try:
            await _execute(session, job)
        except IngestionError as exc:
            session.rollback()
            _fail(session, job, exc.code, exc.message)
        except Exception:
            session.rollback()
            logger.exception("unexpected error running scan %s", job.scan_id)
            _fail(session, job, "ANALYSIS_FAILED", "The analysis did not complete.")
        return True
    finally:
        session.close()


async def worker_loop(stop: asyncio.Event) -> None:
    """Process jobs until ``stop`` is set, sleeping when the queue is empty."""
    logger.info("scan worker %s started", _WORKER_ID)
    while not stop.is_set():
        try:
            processed = await run_next_job()
        except Exception:
            logger.exception("scan worker iteration failed")
            processed = False
        if not processed:
            try:
                await asyncio.wait_for(stop.wait(), timeout=POLL_INTERVAL_SECONDS)
            except TimeoutError:
                pass
    logger.info("scan worker %s stopped", _WORKER_ID)
