"""Unit tests for Phase 10: Migration Review Priority Engine."""

from __future__ import annotations

import unittest

from cryptiq.core.enums import ConfidenceLevel, CryptoRole, PriorityLevel
from cryptiq.priority.scorer import PriorityScorer


class TestPriorityScorer(unittest.TestCase):
    """Verify deterministic scoring and reason generation for Migration Review Priority."""

    def setUp(self):
        self.scorer = PriorityScorer()

    def test_rsa_digital_signature_high_confidence(self):
        """Test Case: RSA + DIGITAL_SIGNATURE + HIGH confidence -> HIGH."""
        finding = {
            "algorithm": "RSA",
            "api": "RSAPrivateKey.sign",
            "confidence": ConfidenceLevel.CONFIRMED,
        }
        result = self.scorer.score(finding=finding, role=CryptoRole.DIGITAL_SIGNATURE)

        self.assertEqual(result.level, PriorityLevel.HIGH)
        self.assertIn("Public-key cryptography", result.reasons)
        self.assertIn("Digital signature operation", result.reasons)
        self.assertIn("High-confidence evidence", result.reasons)
        self.assertIn("Security-relevant operation", result.reasons)

    def test_x25519_key_establishment_high_confidence(self):
        """Test Case: X25519 + KEY_ESTABLISHMENT + HIGH confidence -> HIGH."""
        finding = {
            "algorithm": "X25519",
            "api": "X25519PrivateKey.exchange",
            "confidence": ConfidenceLevel.CONFIRMED,
        }
        result = self.scorer.score(finding=finding, role=CryptoRole.KEY_ESTABLISHMENT)

        self.assertEqual(result.level, PriorityLevel.HIGH)
        self.assertIn("Public-key cryptography", result.reasons)
        self.assertIn("Key establishment operation", result.reasons)
        self.assertIn("High-confidence evidence", result.reasons)
        self.assertIn("Security-relevant operation", result.reasons)

    def test_sha1_hash_deterministic_review_priority(self):
        """Test Case: SHA-1 + HASH -> appropriate deterministic review priority and reasons."""
        finding = {
            "algorithm": "SHA-1",
            "api": "hashlib.sha1",
            "confidence": ConfidenceLevel.CONFIRMED,
        }
        result = self.scorer.score(finding=finding, role=CryptoRole.HASH)

        # Hash is not public-key cryptography; evaluated deterministically
        self.assertIn(result.level, {PriorityLevel.MEDIUM, PriorityLevel.LOW})
        reasons_text = " ".join(result.reasons)
        self.assertIn("Hash function primitive", reasons_text)
        self.assertIn("collision review", reasons_text)
        self.assertNotIn("Public-key cryptography", result.reasons)

    def test_unknown_low_confidence_manual_review(self):
        """Test Case: UNKNOWN + LOW confidence -> deterministic lower/manual-review priority."""
        finding = {
            "algorithm": "UNKNOWN",
            "api": "unknown_call",
            "confidence": ConfidenceLevel.UNKNOWN,
        }
        result = self.scorer.score(finding=finding, role=CryptoRole.UNKNOWN)

        self.assertEqual(result.level, PriorityLevel.LOW)
        reasons_text = " ".join(result.reasons)
        self.assertIn("Unconfirmed or unknown cryptographic primitive", reasons_text)
        self.assertIn("manual triage", reasons_text)

    def test_already_quantum_resistant_pqc(self):
        """Test Case: Direct PQC algorithm observed (e.g. ML-KEM) -> LOW priority."""
        finding = {
            "algorithm": "ML-KEM",
            "api": "mlkem768.encaps",
            "confidence": ConfidenceLevel.CONFIRMED,
        }
        result = self.scorer.score(finding=finding, role=CryptoRole.KEY_ESTABLISHMENT)

        self.assertEqual(result.level, PriorityLevel.LOW)
        reasons_text = " ".join(result.reasons)
        self.assertIn("post-quantum cryptographic primitive observed", reasons_text)

    def test_strict_determinism_across_iterations(self):
        """Verify strict determinism: 100 evaluations on identical input produce identical output."""
        finding = {
            "algorithm": "RSA",
            "api": "RSAPrivateKey.sign",
            "confidence": ConfidenceLevel.CONFIRMED,
        }
        first = self.scorer.score(finding=finding, role=CryptoRole.DIGITAL_SIGNATURE)

        for _ in range(100):
            current = self.scorer.score(finding=finding, role=CryptoRole.DIGITAL_SIGNATURE)
            self.assertEqual(first.level, current.level)
            self.assertEqual(first.score, current.score)
            self.assertEqual(first.reasons, current.reasons)


if __name__ == "__main__":
    unittest.main()
