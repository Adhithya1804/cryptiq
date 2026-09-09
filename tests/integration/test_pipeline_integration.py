"""End-to-end integration test across Phases 9-12."""

from __future__ import annotations

import unittest
from pathlib import Path

from cryptiq.compat.interfaces import AnalysisResult, RuleMatch, SourceSnapshot
from cryptiq.core.enums import (
    ConfidenceLevel,
    CryptoRole,
    ImpactNodeType,
    ImpactRelationship,
    ImpactScope,
    JobStatus,
    PriorityLevel,
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
from cryptiq.worker.service import ScanService
from cryptiq.worker.worker import ScanWorker
from tests.fixtures.sample_contexts import make_sample_rule_matches


class RealSourceProvider:
    def get_snapshot(self, provider: str, owner: str, repository: str, commit_sha: str) -> SourceSnapshot:
        return SourceSnapshot(
            provider=provider,
            owner=owner,
            repository=repository,
            commit_sha=commit_sha,
            source_path=Path("/tmp/pyca-cryptography"),
            retrieval_mode=RetrievalMode.LIVE,
        )


class DeterministicAnalysisEngine:
    def __init__(self, matches=None):
        self.matches = matches or make_sample_rule_matches()
        self.analysis_call_count = 0

    def analyze(self, snapshot: SourceSnapshot) -> AnalysisResult:
        self.analysis_call_count += 1
        return AnalysisResult(
            files_analyzed=15,
            matches=self.matches,
        )


class TestPipelineIntegration(unittest.TestCase):
    """End-to-end test executing Phases 9-12 collaboratively."""

    def setUp(self):
        self.db = Database(":memory:")
        self.conn = self.db.connect()
        self.db.init_schema(self.conn)

        self.scan_repo = ScanRepository(self.conn)
        self.job_repo = JobRepository(self.conn)
        self.finding_repo = FindingRepository(self.conn)

    def tearDown(self):
        self.db.close()

    def test_full_pipeline_queued_to_completed_then_cached(self):
        # 1. Setup initial Scan and ScanJob
        scan_id_1 = "scan-e2e-1"
        job_id_1 = "job-e2e-1"

        scan1 = Scan(
            id=scan_id_1,
            provider="github",
            owner="pyca",
            repository="cryptography",
            commit_sha="1f903f5ed2e5e316f345a927555e48535829d8de",
            parser_version="cryptiq-parser/1.0",
            ruleset_version="rules/1.0",
            pqc_ruleset_version="pqc/1.0",
            status=ScanStatus.QUEUED,
        )
        job1 = ScanJob(
            id=job_id_1,
            scan_id=scan_id_1,
            status=JobStatus.QUEUED,
        )
        self.scan_repo.create(scan1)
        self.job_repo.create(job1)

        engine = DeterministicAnalysisEngine()
        service = ScanService(
            scan_repo=self.scan_repo,
            finding_repo=self.finding_repo,
            source_provider=RealSourceProvider(),
            analysis_engine=engine,
        )
        worker = ScanWorker(job_repo=self.job_repo, scan_service=service, worker_id="integration-worker")

        # 2. Worker executes job 1
        processed = worker.process_next_job()
        self.assertTrue(processed)
        self.assertEqual(engine.analysis_call_count, 1)

        # 3. Verify Scan and Job completed state
        db_job1 = self.job_repo.get_by_id(job_id_1)
        self.assertEqual(db_job1.status, JobStatus.COMPLETED)
        self.assertIsNotNone(db_job1.completed_at)

        db_scan1 = self.scan_repo.get_by_id(scan_id_1)
        self.assertEqual(db_scan1.status, ScanStatus.COMPLETED)
        self.assertEqual(db_scan1.finding_count, 3)
        self.assertEqual(db_scan1.file_count, 15)

        # 4. Verify Phase 9 Impact Graph and Phase 10 Priority in persisted findings
        findings = self.finding_repo.get_findings_by_scan(scan_id_1)
        self.assertEqual(len(findings), 3)

        # Finding 1: RSA signature
        rsa_finding = next(f for f in findings if f.algorithm == "RSA")
        self.assertEqual(rsa_finding.priority, PriorityLevel.HIGH)
        self.assertIn("Public-key cryptography", rsa_finding.priority_reasons)
        self.assertIn("Digital signature operation", rsa_finding.priority_reasons)
        self.assertEqual(len(rsa_finding.fingerprint), 64)

        # Check impact nodes and edges saved in database
        cur = self.conn.execute("SELECT * FROM impact_nodes WHERE finding_id = ?;", (rsa_finding.id,))
        nodes = cur.fetchall()
        node_types = {n["node_type"] for n in nodes}
        self.assertIn(ImpactNodeType.ALGORITHM.value, node_types)
        self.assertIn(ImpactNodeType.API.value, node_types)
        self.assertIn(ImpactNodeType.FUNCTION.value, node_types)
        self.assertIn(ImpactNodeType.CLASS.value, node_types)
        self.assertIn(ImpactNodeType.FILE.value, node_types)

        cur = self.conn.execute("SELECT * FROM impact_edges WHERE finding_id = ?;", (rsa_finding.id,))
        edges = cur.fetchall()
        edge_rels = {e["relationship"] for e in edges}
        self.assertIn(ImpactRelationship.USES.value, edge_rels)
        self.assertIn(ImpactRelationship.CALLS.value, edge_rels)
        self.assertIn(ImpactRelationship.CONTAINS.value, edge_rels)
        self.assertIn(ImpactRelationship.DEFINED_IN.value, edge_rels)

        # Finding 2: X25519 key establishment
        x25519_finding = next(f for f in findings if f.algorithm == "X25519")
        self.assertEqual(x25519_finding.priority, PriorityLevel.HIGH)
        self.assertIn("Key establishment operation", x25519_finding.priority_reasons)

        # 5. Subsequent Scan with Identical Identity triggers CACHED_REAL (Phase 11)
        scan2, job2, is_cache_hit = service.request_scan(
            provider="github",
            owner="pyca",
            repository="cryptography",
            commit_sha="1f903f5ed2e5e316f345a927555e48535829d8de",
            parser_version="cryptiq-parser/1.0",
            ruleset_version="rules/1.0",
            pqc_ruleset_version="pqc/1.0",
            job_repo=self.job_repo,
        )
        self.assertTrue(is_cache_hit)
        self.assertEqual(scan2.id, scan_id_1)
        self.assertEqual(scan2.retrieval_mode, RetrievalMode.CACHED_REAL)
        self.assertEqual(scan2.status, ScanStatus.COMPLETED)
        self.assertIsNone(job2)  # No job needed since already cached!

        # Analysis engine MUST NOT be called again (cache hit!)
        self.assertEqual(engine.analysis_call_count, 1)


if __name__ == "__main__":
    unittest.main()
