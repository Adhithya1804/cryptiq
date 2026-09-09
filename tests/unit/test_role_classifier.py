import unittest

from app.engine.models import (
    Confidence,
    CryptoRole,
    ParsedFile,
    RawObservation,
    RoleInference,
)
from app.engine.roles.classifier import RoleClassifier


class TestRoleClassifier(unittest.TestCase):

    def setUp(self):
        self.classifier = RoleClassifier()

    def test_acceptance_criteria_rsa_sign_digital_signature_high(self):
        """
        Acceptance Criteria:
        RSAPrivateKey.sign() results in DIGITAL_SIGNATURE (HIGH).
        """
        obs = RawObservation(
            algorithm="RSA",
            library="cryptography",
            api="RSAPrivateKey.sign",
            operation="SIGN",
            primitive="ASYMMETRIC",
            metadata={"padding": "PSS", "hash_algorithm": "SHA256"},
        )
        inference = self.classifier.classify(obs)
        self.assertEqual(inference.role, CryptoRole.DIGITAL_SIGNATURE)
        self.assertEqual(inference.confidence, Confidence.HIGH)
        self.assertEqual(inference.hierarchy_level, "EXPLICIT_API")

    def test_acceptance_criteria_x25519_exchange_key_establishment_high(self):
        """
        Acceptance Criteria:
        X25519PrivateKey.exchange() results in KEY_ESTABLISHMENT (HIGH).
        """
        obs = RawObservation(
            algorithm="X25519",
            library="cryptography",
            api="X25519PrivateKey.exchange",
            operation="KEY_EXCHANGE",
            primitive="ASYMMETRIC",
        )
        inference = self.classifier.classify(obs)
        self.assertEqual(inference.role, CryptoRole.KEY_ESTABLISHMENT)
        self.assertEqual(inference.confidence, Confidence.HIGH)
        self.assertEqual(inference.hierarchy_level, "EXPLICIT_API")

    def test_acceptance_criteria_ambiguous_encrypt_unknown_low(self):
        """
        Acceptance Criteria:
        An ambiguous encrypt() call defaults to UNKNOWN (LOW).
        """
        obs = RawObservation(
            algorithm="UNKNOWN",
            library="",
            api="some_variable.encrypt",
            operation="ENCRYPT",
        )
        inference = self.classifier.classify(obs)
        self.assertEqual(inference.role, CryptoRole.UNKNOWN)
        self.assertEqual(inference.confidence, Confidence.LOW)
        self.assertEqual(inference.hierarchy_level, "UNKNOWN")

    def test_failure_condition_no_blind_rsa_mapping(self):
        """
        Failure Condition:
        The classifier must NOT map 'RSA' blindly to DIGITAL_SIGNATURE without
        checking the API or operation fields.
        """
        # Standalone keygen or ambiguous RSA without operation
        keygen_obs = RawObservation(
            algorithm="RSA",
            library="cryptography",
            api="rsa.generate_private_key",
            operation="KEYGEN",
        )
        inference = self.classifier.classify(keygen_obs)
        # Standalone RSA keygen is dual-use and must NOT be forced into DIGITAL_SIGNATURE
        self.assertEqual(inference.role, CryptoRole.UNKNOWN)
        self.assertEqual(inference.confidence, Confidence.LOW)

    def test_rsa_decrypt_oaep_key_establishment(self):
        """
        RSA encryption/decryption (OAEP/PKCS1v15) represents key transport / key establishment.
        """
        obs = RawObservation(
            algorithm="RSA",
            library="cryptography",
            api="RSAPrivateKey.decrypt",
            operation="DECRYPT",
            metadata={"padding": "OAEP"},
        )
        inference = self.classifier.classify(obs)
        self.assertEqual(inference.role, CryptoRole.KEY_ESTABLISHMENT)
        self.assertEqual(inference.confidence, Confidence.HIGH)

    def test_aes_symmetric_encryption_high(self):
        """
        AES cipher operation classifies as SYMMETRIC_ENCRYPTION (HIGH).
        """
        obs = RawObservation(
            algorithm="AES",
            library="cryptography",
            api="algorithms.AES",
            operation="SYMMETRIC_ENCRYPTION",
            primitive="SYMMETRIC",
            metadata={"mode": "GCM"},
        )
        inference = self.classifier.classify(obs)
        self.assertEqual(inference.role, CryptoRole.SYMMETRIC_ENCRYPTION)
        self.assertEqual(inference.confidence, Confidence.HIGH)

    def test_hash_classification_high(self):
        """
        Cryptographic hashes classify as HASH (HIGH).
        """
        obs = RawObservation(
            algorithm="SHA-256",
            library="cryptography",
            api="hashes.SHA256",
            operation="HASH",
            primitive="HASH",
        )
        inference = self.classifier.classify(obs)
        self.assertEqual(inference.role, CryptoRole.HASH)
        self.assertEqual(inference.confidence, Confidence.HIGH)

    def test_object_context_medium_confidence(self):
        """
        When API name is generic but symbol table establishes key type,
        classify via Object Context with MEDIUM confidence.
        """
        obs = RawObservation(
            algorithm="UNKNOWN",
            library="cryptography",
            api="client_key.sign",
            operation="SIGN",
            metadata={"receiver_name": "client_key"},
        )
        parsed_file = ParsedFile(
            symbols={"client_key": "Ed25519PrivateKey"}
        )
        inference = self.classifier.classify(obs, parsed_file)
        self.assertEqual(inference.role, CryptoRole.DIGITAL_SIGNATURE)
        self.assertEqual(inference.confidence, Confidence.MEDIUM)
        self.assertEqual(inference.hierarchy_level, "OBJECT_CONTEXT")

    def test_malformed_observation_safe_fallback(self):
        """
        Security requirement: Malformed observations default safely to UNKNOWN / LOW.
        """
        inference = self.classifier.classify(None)  # type: ignore
        self.assertEqual(inference.role, CryptoRole.UNKNOWN)
        self.assertEqual(inference.confidence, Confidence.LOW)


if __name__ == "__main__":
    unittest.main()
