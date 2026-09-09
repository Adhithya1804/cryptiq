import unittest

from app.engine.models import CryptoRole, MigrationPath
from app.engine.pqc.mapper import PQCMapper, map_review_path


class TestPQCMapper(unittest.TestCase):

    def setUp(self):
        self.mapper = PQCMapper(pqc_ruleset_version="0.1.0")

    def test_acceptance_criteria_rsa_key_establishment_ml_kem(self):
        """
        Acceptance Criteria:
        Calling mapper.map("RSA", CryptoRole.KEY_ESTABLISHMENT) returns a MigrationPath pointing to ML-KEM.
        """
        path = self.mapper.map("RSA", CryptoRole.KEY_ESTABLISHMENT)
        self.assertIsInstance(path, MigrationPath)
        self.assertEqual(path.review_path, ["ML-KEM"])
        self.assertIn("ML-KEM", path)
        self.assertEqual(path.pqc_ruleset_version, "0.1.0")

    def test_acceptance_criteria_rsa_digital_signature_ml_dsa_slh_dsa(self):
        """
        Acceptance Criteria:
        Calling mapper.map("RSA", CryptoRole.DIGITAL_SIGNATURE) returns ML-DSA / SLH-DSA.
        """
        path = self.mapper.map("RSA", CryptoRole.DIGITAL_SIGNATURE)
        self.assertIsInstance(path, MigrationPath)
        self.assertEqual(path.review_path, ["ML-DSA", "SLH-DSA"])
        self.assertEqual(path.display_path, "ML-DSA / SLH-DSA")
        self.assertIn("ML-DSA", path)
        self.assertIn("SLH-DSA", path)

    def test_failure_condition_role_determines_path(self):
        """
        Failure Condition:
        The mapper must NOT return ML-KEM for all RSA operations, ignoring the role parameter.
        """
        sig_path = self.mapper.map("RSA", CryptoRole.DIGITAL_SIGNATURE)
        kex_path = self.mapper.map("RSA", CryptoRole.KEY_ESTABLISHMENT)

        self.assertNotEqual(sig_path.review_path, kex_path.review_path)
        self.assertEqual(sig_path.review_path, ["ML-DSA", "SLH-DSA"])
        self.assertEqual(kex_path.review_path, ["ML-KEM"])

    def test_ecdsa_and_ed25519_signatures(self):
        """ECDSA and Ed25519 signatures map to ML-DSA / SLH-DSA."""
        ecdsa_path = self.mapper.map("ECDSA", CryptoRole.DIGITAL_SIGNATURE)
        ed_path = self.mapper.map("Ed25519", CryptoRole.DIGITAL_SIGNATURE)

        self.assertEqual(ecdsa_path.review_path, ["ML-DSA", "SLH-DSA"])
        self.assertEqual(ed_path.review_path, ["ML-DSA", "SLH-DSA"])

    def test_ecdh_and_x25519_key_exchange(self):
        """ECDH and X25519 key agreements map to ML-KEM."""
        ecdh_path = self.mapper.map("ECDH", CryptoRole.KEY_ESTABLISHMENT)
        x25519_path = self.mapper.map("X25519", CryptoRole.KEY_ESTABLISHMENT)

        self.assertEqual(ecdh_path.review_path, ["ML-KEM"])
        self.assertEqual(x25519_path.review_path, ["ML-KEM"])

    def test_symmetric_and_hash_policies(self):
        """Symmetric encryption and hashing map to policy reviews."""
        aes_path = self.mapper.map("AES", CryptoRole.SYMMETRIC_ENCRYPTION)
        hash_path = self.mapper.map("SHA-256", CryptoRole.HASH)

        self.assertEqual(aes_path.review_path, ["Key/implementation review"])
        self.assertEqual(hash_path.review_path, ["Hash/policy review"])

    def test_unknown_maps_to_manual_review(self):
        """Unknown or ambiguous combinations map to Manual review."""
        unknown_path = self.mapper.map("custom_algo", CryptoRole.UNKNOWN)
        self.assertEqual(unknown_path.review_path, ["Manual review"])

    def test_version_injection(self):
        """PQCMapper respects injected pqc_ruleset_version."""
        custom_mapper = PQCMapper(pqc_ruleset_version="0.2.0-preview")
        path = custom_mapper.map("RSA", CryptoRole.DIGITAL_SIGNATURE)
        self.assertEqual(path.pqc_ruleset_version, "0.2.0-preview")

    def test_standalone_helper(self):
        """Verify map_review_path helper function."""
        path = map_review_path("X25519", CryptoRole.KEY_ESTABLISHMENT)
        self.assertEqual(path.review_path, ["ML-KEM"])


if __name__ == "__main__":
    unittest.main()
