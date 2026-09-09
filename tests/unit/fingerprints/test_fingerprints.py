"""Unit tests for Phase 11: Finding Fingerprints and Scan Caching."""

from __future__ import annotations

import sqlite3
import unittest
from datetime import datetime, timezone

from cryptiq.cache.fingerprint import FingerprintEngine
from cryptiq.cache.identity import ScanCacheManager, ScanIdentity
from cryptiq.core.enums import RetrievalMode, ScanStatus
from cryptiq.core.models import Scan
from cryptiq.storage.db import Database
from cryptiq.storage.repositories import ScanRepository


class TestFindingFingerprint(unittest.TestCase):
    """Verify stability and variation sensitivity of finding fingerprints."""

    def test_fingerprint_stability_identical_inputs(self):
        """Identical identity fields produce the exact same fingerprint."""
        fp1 = FingerprintEngine.compute(
            repository="pyca/cryptography",
            commit_sha="1f903f5ed2e5e316f345a927555e48535829d8de",
            file_path="src/certificates/signing.py",
            start_line=54,
            rule_id="python.rsa",
            algorithm="RSA",
            api="RSAPrivateKey.sign",
        )

        fp2 = FingerprintEngine.compute(
            repository="pyca/cryptography",
            commit_sha="1f903f5ed2e5e316f345a927555e48535829d8de",
            file_path="src/certificates/signing.py",
            start_line=54,
            rule_id="python.rsa",
            algorithm="RSA",
            api="RSAPrivateKey.sign",
        )

        self.assertEqual(fp1, fp2)
        self.assertEqual(len(fp1), 64)  # sha256 hex length

    def test_fingerprint_changes_on_different_commit(self):
        base = FingerprintEngine.compute(
            repository="pyca/cryptography",
            commit_sha="1111111111111111111111111111111111111111",
            file_path="src/signing.py",
            start_line=10,
            rule_id="python.rsa",
            algorithm="RSA",
            api="RSAPrivateKey.sign",
        )
        diff = FingerprintEngine.compute(
            repository="pyca/cryptography",
            commit_sha="2222222222222222222222222222222222222222",
            file_path="src/signing.py",
            start_line=10,
            rule_id="python.rsa",
            algorithm="RSA",
            api="RSAPrivateKey.sign",
        )
        self.assertNotEqual(base, diff)

    def test_fingerprint_changes_on_different_file(self):
        base = FingerprintEngine.compute(
            repository="pyca/cryptography",
            commit_sha="1111111111111111111111111111111111111111",
            file_path="src/file_a.py",
            start_line=10,
            rule_id="python.rsa",
            algorithm="RSA",
            api="RSAPrivateKey.sign",
        )
        diff = FingerprintEngine.compute(
            repository="pyca/cryptography",
            commit_sha="1111111111111111111111111111111111111111",
            file_path="src/file_b.py",
            start_line=10,
            rule_id="python.rsa",
            algorithm="RSA",
            api="RSAPrivateKey.sign",
        )
        self.assertNotEqual(base, diff)

    def test_fingerprint_changes_on_different_line(self):
        base = FingerprintEngine.compute(
            repository="pyca/cryptography",
            commit_sha="1111111111111111111111111111111111111111",
            file_path="src/file_a.py",
            start_line=10,
            rule_id="python.rsa",
            algorithm="RSA",
            api="RSAPrivateKey.sign",
        )
        diff = FingerprintEngine.compute(
            repository="pyca/cryptography",
            commit_sha="1111111111111111111111111111111111111111",
            file_path="src/file_a.py",
            start_line=25,
            rule_id="python.rsa",
            algorithm="RSA",
            api="RSAPrivateKey.sign",
        )
        self.assertNotEqual(base, diff)

    def test_fingerprint_changes_on_different_rule(self):
        base = FingerprintEngine.compute(
            repository="pyca/cryptography",
            commit_sha="1111111111111111111111111111111111111111",
            file_path="src/file_a.py",
            start_line=10,
            rule_id="python.rsa",
            algorithm="RSA",
            api="RSAPrivateKey.sign",
        )
        diff = FingerprintEngine.compute(
            repository="pyca/cryptography",
            commit_sha="1111111111111111111111111111111111111111",
            file_path="src/file_a.py",
            start_line=10,
            rule_id="python.ec_ecdsa",
            algorithm="RSA",
            api="RSAPrivateKey.sign",
        )
        self.assertNotEqual(base, diff)

    def test_fingerprint_changes_on_different_api(self):
        base = FingerprintEngine.compute(
            repository="pyca/cryptography",
            commit_sha="1111111111111111111111111111111111111111",
            file_path="src/file_a.py",
            start_line=10,
            rule_id="python.rsa",
            algorithm="RSA",
            api="RSAPrivateKey.sign",
        )
        diff = FingerprintEngine.compute(
            repository="pyca/cryptography",
            commit_sha="1111111111111111111111111111111111111111",
            file_path="src/file_a.py",
            start_line=10,
            rule_id="python.rsa",
            algorithm="RSA",
            api="RSAPublicKey.verify",
        )
        self.assertNotEqual(base, diff)


class TestScanCaching(unittest.TestCase):
    """Verify deterministic scan caching, identity matching, and version invalidation."""

    def setUp(self):
        self.db = Database(":memory:")
        self.conn = self.db.connect()
        self.db.init_schema(self.conn)
        self.scan_repo = ScanRepository(self.conn)

    def tearDown(self):
        self.db.close()

    def test_cache_hit_returns_cached_real(self):
        """Cache hit on identical completed scan returns CACHED_REAL."""
        completed_scan = Scan(
            id="scan-1",
            provider="github",
            owner="pyca",
            repository="cryptography",
            commit_sha="1f903f5ed2e5e316f345a927555e48535829d8de",
            parser_version="cryptiq-parser/1.0",
            ruleset_version="rules/1.0",
            pqc_ruleset_version="pqc/1.0",
            status=ScanStatus.COMPLETED,
            retrieval_mode=RetrievalMode.LIVE,
            file_count=50,
            finding_count=12,
            completed_at=datetime.now(timezone.utc),
        )
        self.scan_repo.create(completed_scan)

        identity = ScanIdentity(
            provider="github",
            owner="pyca",
            repository="cryptography",
            commit_sha="1f903f5ed2e5e316f345a927555e48535829d8de",
            parser_version="cryptiq-parser/1.0",
            ruleset_version="rules/1.0",
            pqc_ruleset_version="pqc/1.0",
        )

        cached = ScanCacheManager.get_cached_scan(identity, self.scan_repo)
        self.assertIsNotNone(cached)
        self.assertEqual(cached.id, "scan-1")
        self.assertEqual(cached.retrieval_mode, RetrievalMode.CACHED_REAL)
        self.assertEqual(cached.status, ScanStatus.COMPLETED)

    def test_cache_miss_different_commit(self):
        """Different commit_sha results in cache miss."""
        completed_scan = Scan(
            id="scan-1",
            provider="github",
            owner="pyca",
            repository="cryptography",
            commit_sha="1f903f5ed2e5e316f345a927555e48535829d8de",
            parser_version="cryptiq-parser/1.0",
            ruleset_version="rules/1.0",
            pqc_ruleset_version="pqc/1.0",
            status=ScanStatus.COMPLETED,
            retrieval_mode=RetrievalMode.LIVE,
        )
        self.scan_repo.create(completed_scan)

        diff_commit_identity = ScanIdentity(
            provider="github",
            owner="pyca",
            repository="cryptography",
            commit_sha="aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            parser_version="cryptiq-parser/1.0",
            ruleset_version="rules/1.0",
            pqc_ruleset_version="pqc/1.0",
        )

        cached = ScanCacheManager.get_cached_scan(diff_commit_identity, self.scan_repo)
        self.assertIsNone(cached)

    def test_version_invalidation(self):
        """Different parser_version, ruleset_version, or pqc_ruleset_version invalidates cache."""
        completed_scan = Scan(
            id="scan-1",
            provider="github",
            owner="pyca",
            repository="cryptography",
            commit_sha="1f903f5ed2e5e316f345a927555e48535829d8de",
            parser_version="cryptiq-parser/1.0",
            ruleset_version="rules/1.0",
            pqc_ruleset_version="pqc/1.0",
            status=ScanStatus.COMPLETED,
            retrieval_mode=RetrievalMode.LIVE,
        )
        self.scan_repo.create(completed_scan)

        # Different parser version
        id_diff_parser = ScanIdentity(
            provider="github",
            owner="pyca",
            repository="cryptography",
            commit_sha="1f903f5ed2e5e316f345a927555e48535829d8de",
            parser_version="cryptiq-parser/2.0",
            ruleset_version="rules/1.0",
            pqc_ruleset_version="pqc/1.0",
        )
        self.assertIsNone(ScanCacheManager.get_cached_scan(id_diff_parser, self.scan_repo))

        # Different ruleset version
        id_diff_ruleset = ScanIdentity(
            provider="github",
            owner="pyca",
            repository="cryptography",
            commit_sha="1f903f5ed2e5e316f345a927555e48535829d8de",
            parser_version="cryptiq-parser/1.0",
            ruleset_version="rules/1.1",
            pqc_ruleset_version="pqc/1.0",
        )
        self.assertIsNone(ScanCacheManager.get_cached_scan(id_diff_ruleset, self.scan_repo))

        # Different PQC ruleset version
        id_diff_pqc = ScanIdentity(
            provider="github",
            owner="pyca",
            repository="cryptography",
            commit_sha="1f903f5ed2e5e316f345a927555e48535829d8de",
            parser_version="cryptiq-parser/1.0",
            ruleset_version="rules/1.0",
            pqc_ruleset_version="pqc/2.0",
        )
        self.assertIsNone(ScanCacheManager.get_cached_scan(id_diff_pqc, self.scan_repo))

    def test_failed_scan_is_never_cache_hit(self):
        """A failed scan must NOT be treated as a successful cached result."""
        failed_scan = Scan(
            id="scan-failed",
            provider="github",
            owner="pyca",
            repository="cryptography",
            commit_sha="1f903f5ed2e5e316f345a927555e48535829d8de",
            parser_version="cryptiq-parser/1.0",
            ruleset_version="rules/1.0",
            pqc_ruleset_version="pqc/1.0",
            status=ScanStatus.FAILED,
            retrieval_mode=RetrievalMode.LIVE,
            error_code="PARSER_ERROR",
        )
        self.scan_repo.create(failed_scan)

        identity = ScanIdentity(
            provider="github",
            owner="pyca",
            repository="cryptography",
            commit_sha="1f903f5ed2e5e316f345a927555e48535829d8de",
            parser_version="cryptiq-parser/1.0",
            ruleset_version="rules/1.0",
            pqc_ruleset_version="pqc/1.0",
        )

        cached = ScanCacheManager.get_cached_scan(identity, self.scan_repo)
        self.assertIsNone(cached)

    def test_unique_constraint_on_completed_scan_identity(self):
        """Database constraint prevents duplicate completed scans with identical identity."""
        scan1 = Scan(
            id="scan-1",
            provider="github",
            owner="pyca",
            repository="cryptography",
            commit_sha="1f903f5ed2e5e316f345a927555e48535829d8de",
            parser_version="cryptiq-parser/1.0",
            ruleset_version="rules/1.0",
            pqc_ruleset_version="pqc/1.0",
            status=ScanStatus.COMPLETED,
        )
        self.scan_repo.create(scan1)

        scan2 = Scan(
            id="scan-2",
            provider="github",
            owner="pyca",
            repository="cryptography",
            commit_sha="1f903f5ed2e5e316f345a927555e48535829d8de",
            parser_version="cryptiq-parser/1.0",
            ruleset_version="rules/1.0",
            pqc_ruleset_version="pqc/1.0",
            status=ScanStatus.COMPLETED,
        )
        with self.assertRaises(sqlite3.IntegrityError):
            self.scan_repo.create(scan2)


if __name__ == "__main__":
    unittest.main()
