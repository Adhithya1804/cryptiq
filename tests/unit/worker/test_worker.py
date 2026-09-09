"""Unit tests for Phase 12: Database-backed Scan Worker."""

from __future__ import annotations

import sqlite3
import unittest
from pathlib import Path
from unittest.mock import MagicMock

from cryptiq.compat.interfaces import AnalysisResult, RuleMatch, SourceSnapshot
from cryptiq.core.enums import (
    ConfidenceLevel,
    CryptoRole,
    ErrorCode,
    JobStatus,
    RetrievalMode,
    ScanStatus,
)
from cryptiq.core.models import Scan, ScanJob
from cryptiq.storage.db import Database
from cryptiq.storage.repositories import (
    FindingRepository,
    JobRepository,
    ScanRepository,
)
from cryptiq.worker.job import (
    InvalidStateTransitionError,
    JobStateMachine,
)
from cryptiq.worker.service import ScanService
from cryptiq.worker.worker import ScanWorker


class DummySourceProvider:
    """Mock source provider for worker tests."""

    def get_snapshot(self, provider: str, owner: str, repository: str, commit_sha: str) -> SourceSnapshot:
        return SourceSnapshot(
            provider=provider,
            owner=owner,
            repository=repository,
            commit_sha=commit_sha,
            source_path=Path("/tmp/dummy"),
            retrieval_mode=RetrievalMode.LIVE,
        )


class DummyAnalysisEngine:
    """Mock analysis engine for worker tests."""

    def __init__(self, matches=None, fail_with=None):
        self.matches = matches or []
        self.fail_with = fail_with

    def analyze(self, snapshot: SourceSnapshot) -> AnalysisResult:
        if self.fail_with:
            raise self.fail_with
        return AnalysisResult(
            files_analyzed=5,
            matches=self.matches,
        )


class TestJobStateMachine(unittest.TestCase):
    """Verify state machine transitions and retry logic."""

    def test_legal_transitions(self):
        # QUEUED -> RUNNING
        JobStateMachine.validate_transition(JobStatus.QUEUED, JobStatus.RUNNING)
        # RUNNING -> COMPLETED
        JobStateMachine.validate_transition(JobStatus.RUNNING, JobStatus.COMPLETED)
        # RUNNING -> FAILED
        JobStateMachine.validate_transition(JobStatus.RUNNING, JobStatus.FAILED)
        # RUNNING -> QUEUED (retry)
        JobStateMachine.validate_transition(JobStatus.RUNNING, JobStatus.QUEUED)

    def test_illegal_transitions_raise_error(self):
        # COMPLETED -> RUNNING
        with self.assertRaises(InvalidStateTransitionError):
            JobStateMachine.validate_transition(JobStatus.COMPLETED, JobStatus.RUNNING)
        # FAILED -> COMPLETED
        with self.assertRaises(InvalidStateTransitionError):
            JobStateMachine.validate_transition(JobStatus.FAILED, JobStatus.COMPLETED)

    def test_should_retry_boundary(self):
        job = ScanJob(id="j-1", scan_id="s-1", attempt_count=1, max_attempts=3)
        self.assertTrue(JobStateMachine.should_retry(job))

        job.attempt_count = 2
        self.assertTrue(JobStateMachine.should_retry(job))

        job.attempt_count = 3
        self.assertFalse(JobStateMachine.should_retry(job))


class TestScanWorker(unittest.TestCase):
    """Verify worker claiming, execution, retries, error handling, and transactional persistence."""

    def setUp(self):
        self.db = Database(":memory:")
        self.conn = self.db.connect()
        self.db.init_schema(self.conn)

        self.scan_repo = ScanRepository(self.conn)
        self.job_repo = JobRepository(self.conn)
        self.finding_repo = FindingRepository(self.conn)

    def tearDown(self):
        self.db.close()

    def _create_scan_and_job(self, scan_id="scan-1", job_id="job-1", max_attempts=3):
        scan = Scan(
            id=scan_id,
            provider="github",
            owner="pyca",
            repository="cryptography",
            commit_sha="1f903f5ed2e5e316f345a927555e48535829d8de",
            parser_version="cryptiq-parser/1.0",
            ruleset_version="rules/1.0",
            pqc_ruleset_version="pqc/1.0",
            status=ScanStatus.QUEUED,
        )
        job = ScanJob(
            id=job_id,
            scan_id=scan_id,
            status=JobStatus.QUEUED,
            max_attempts=max_attempts,
        )
        self.scan_repo.create(scan)
        self.job_repo.create(job)
        return scan, job

    def test_job_claiming(self):
        """QUEUED job is claimed, transitioning to RUNNING with worker identity and lock timestamp."""
        self._create_scan_and_job()

        service = ScanService(
            scan_repo=self.scan_repo,
            finding_repo=self.finding_repo,
            source_provider=DummySourceProvider(),
            analysis_engine=DummyAnalysisEngine(),
        )
        worker = ScanWorker(job_repo=self.job_repo, scan_service=service, worker_id="worker-test-1")

        claimed = worker.claim_job()
        self.assertIsNotNone(claimed)
        self.assertEqual(claimed.id, "job-1")
        self.assertEqual(claimed.status, JobStatus.RUNNING)
        self.assertEqual(claimed.locked_by, "worker-test-1")
        self.assertIsNotNone(claimed.locked_at)
        self.assertEqual(claimed.attempt_count, 1)

    def test_duplicate_claim_protection(self):
        """A job already claimed by Worker 1 cannot simultaneously be claimed by Worker 2."""
        self._create_scan_and_job()

        service = ScanService(
            scan_repo=self.scan_repo,
            finding_repo=self.finding_repo,
            source_provider=DummySourceProvider(),
            analysis_engine=DummyAnalysisEngine(),
        )
        w1 = ScanWorker(job_repo=self.job_repo, scan_service=service, worker_id="worker-1")
        w2 = ScanWorker(job_repo=self.job_repo, scan_service=service, worker_id="worker-2")

        c1 = w1.claim_job()
        self.assertIsNotNone(c1)

        c2 = w2.claim_job()
        self.assertIsNone(c2)  # Already locked by worker-1

    def test_successful_execution_and_result_persistence(self):
        """RUNNING job executes analysis, persists findings/evidence/impact, and completes."""
        self._create_scan_and_job()

        matches = [
            RuleMatch(
                rule_id="python.rsa",
                algorithm="RSA",
                api="RSAPrivateKey.sign",
                file_path="src/signing.py",
                start_line=42,
                end_line=42,
                confidence=ConfidenceLevel.CONFIRMED,
                role=CryptoRole.DIGITAL_SIGNATURE,
                code_snippet="key.sign()",
                function_name="sign_cert",
                class_name="Signer",
            )
        ]
        service = ScanService(
            scan_repo=self.scan_repo,
            finding_repo=self.finding_repo,
            source_provider=DummySourceProvider(),
            analysis_engine=DummyAnalysisEngine(matches=matches),
        )
        worker = ScanWorker(job_repo=self.job_repo, scan_service=service)

        processed = worker.process_next_job()
        self.assertTrue(processed)

        # Verify Job state
        job = self.job_repo.get_by_id("job-1")
        self.assertEqual(job.status, JobStatus.COMPLETED)
        self.assertIsNotNone(job.completed_at)
        self.assertIsNone(job.locked_by)

        # Verify Scan state
        scan = self.scan_repo.get_by_id("scan-1")
        self.assertEqual(scan.status, ScanStatus.COMPLETED)
        self.assertEqual(scan.finding_count, 1)
        self.assertEqual(scan.file_count, 5)

        # Verify Findings persistence
        findings = self.finding_repo.get_findings_by_scan("scan-1")
        self.assertEqual(len(findings), 1)
        f = findings[0]
        self.assertEqual(f.algorithm, "RSA")
        self.assertEqual(f.role, CryptoRole.DIGITAL_SIGNATURE)
        self.assertTrue(len(f.fingerprint) == 64)

    def test_retry_on_recoverable_failure(self):
        """Attempt 1 fails -> job is re-queued for retry with attempt_count=1 and last_error recorded."""
        self._create_scan_and_job(max_attempts=3)

        service = ScanService(
            scan_repo=self.scan_repo,
            finding_repo=self.finding_repo,
            source_provider=DummySourceProvider(),
            analysis_engine=DummyAnalysisEngine(fail_with=RuntimeError("Transient network timeout")),
        )
        worker = ScanWorker(job_repo=self.job_repo, scan_service=service)

        processed = worker.process_next_job()
        self.assertTrue(processed)

        job = self.job_repo.get_by_id("job-1")
        # Attempt 1 failed < max_attempts 3 -> QUEUED for retry
        self.assertEqual(job.status, JobStatus.QUEUED)
        self.assertEqual(job.attempt_count, 1)
        self.assertIn("Transient network timeout", job.last_error)
        self.assertIsNone(job.locked_by)

    def test_permanent_failure_when_max_attempts_reached(self):
        """When max attempts is reached, job transitions to FAILED and scan is marked FAILED."""
        self._create_scan_and_job(max_attempts=1)

        service = ScanService(
            scan_repo=self.scan_repo,
            finding_repo=self.finding_repo,
            source_provider=DummySourceProvider(),
            analysis_engine=DummyAnalysisEngine(fail_with=ValueError("Fatal parser syntax error")),
        )
        worker = ScanWorker(job_repo=self.job_repo, scan_service=service)

        worker.process_next_job()

        job = self.job_repo.get_by_id("job-1")
        self.assertEqual(job.status, JobStatus.FAILED)
        self.assertEqual(job.attempt_count, 1)

        scan = self.scan_repo.get_by_id("scan-1")
        self.assertEqual(scan.status, ScanStatus.FAILED)
        self.assertEqual(scan.error_code, ErrorCode.PARSER_ERROR.value)

    def test_exception_isolation_across_multiple_jobs(self):
        """A failing job does not terminate the worker loop; subsequent jobs continue processing."""
        # Create Job 1 (will fail)
        self._create_scan_and_job("scan-fail", "job-fail", max_attempts=1)
        # Create Job 2 (will succeed)
        self._create_scan_and_job("scan-ok", "job-ok", max_attempts=1)

        call_count = 0

        class FlakyEngine:
            def analyze(self, snapshot):
                nonlocal call_count
                call_count += 1
                if snapshot.repository == "cryptography" and call_count == 1:
                    raise RuntimeError("Parser failure on job 1")
                return AnalysisResult(files_analyzed=1, matches=[])

        service = ScanService(
            scan_repo=self.scan_repo,
            finding_repo=self.finding_repo,
            source_provider=DummySourceProvider(),
            analysis_engine=FlakyEngine(),
        )
        worker = ScanWorker(job_repo=self.job_repo, scan_service=service)

        # Worker processes job 1 (fails)
        processed1 = worker.process_next_job()
        self.assertTrue(processed1)

        # Worker processes job 2 (succeeds!)
        processed2 = worker.process_next_job()
        self.assertTrue(processed2)

        job1 = self.job_repo.get_by_id("job-fail")
        job2 = self.job_repo.get_by_id("job-ok")
        self.assertEqual(job1.status, JobStatus.FAILED)
        self.assertEqual(job2.status, JobStatus.COMPLETED)

    def test_transactional_persistence_failure_does_not_leave_completed_scan(self):
        """Simulated persistence error rolls back and does not leave a falsely completed scan."""
        self._create_scan_and_job("scan-tx", "job-tx", max_attempts=1)

        matches = [
            RuleMatch(
                rule_id="python.rsa",
                algorithm="RSA",
                api="RSAPrivateKey.sign",
                file_path="src/signing.py",
                start_line=1,
                end_line=1,
            )
        ]

        # Mock FindingRepository to raise an exception during batch save
        failing_finding_repo = MagicMock(spec=FindingRepository)
        failing_finding_repo.save_findings_batch.side_effect = sqlite3.OperationalError("Disk I/O error")

        service = ScanService(
            scan_repo=self.scan_repo,
            finding_repo=failing_finding_repo,
            source_provider=DummySourceProvider(),
            analysis_engine=DummyAnalysisEngine(matches=matches),
        )
        worker = ScanWorker(job_repo=self.job_repo, scan_service=service)

        worker.process_next_job()

        scan = self.scan_repo.get_by_id("scan-tx")
        # Scan MUST NOT be marked completed
        self.assertNotEqual(scan.status, ScanStatus.COMPLETED)
        self.assertEqual(scan.status, ScanStatus.FAILED)


if __name__ == "__main__":
    unittest.main()
