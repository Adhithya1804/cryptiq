import ast
import unittest

from app.engine.evidence.extractor import EvidenceExtractor
from app.engine.models import AnalysisContext, RawObservation, RuleMatch
from app.engine.rules.base import CryptoRule
from app.engine.rules.rsa import RSARule


class TestRSARuleAndEvidence(unittest.TestCase):

    def setUp(self):
        self.rule = RSARule()
        self.extractor = EvidenceExtractor()

    def test_protocol_conformance(self):
        """Verify RSARule implements CryptoRule protocol."""
        self.assertIsInstance(self.rule, CryptoRule)
        self.assertEqual(self.rule.rule_id, "PY-CRYPTO-RSA")

    def test_acceptance_criteria_rsa_sign_pss(self):
        """
        Acceptance Criteria:
        RSARule successfully identifies private_key.sign(..., padding.PSS(...), hashes.SHA256())
        and EvidenceExtractor returns the exact source lines.
        """
        code = (
            "from cryptography.hazmat.primitives.asymmetric import padding\n"
            "from cryptography.hazmat.primitives import hashes\n"
            "\n"
            "def create_signature(private_key, payload):\n"
            "    sig = private_key.sign(\n"
            "        payload,\n"
            "        padding.PSS(\n"
            "            mgf=padding.MGF1(hashes.SHA256()),\n"
            "            salt_length=padding.PSS.MAX_LENGTH,\n"
            "        ),\n"
            "        hashes.SHA256(),\n"
            "    )\n"
            "    return sig\n"
        )
        context = AnalysisContext.from_source(code, file_path="src/crypto_service.py")
        tree = ast.parse(code)

        matches: list[RuleMatch] = []
        for node in ast.walk(tree):
            match = self.rule.evaluate(node, context)
            if match is not None:
                matches.append(match)

        self.assertEqual(len(matches), 1)
        match = matches[0]

        # Verify RawObservation
        obs = match.observation
        self.assertIsInstance(obs, RawObservation)
        self.assertEqual(obs.algorithm, "RSA")
        self.assertEqual(obs.library, "cryptography")
        self.assertEqual(obs.api, "RSAPrivateKey.sign")
        self.assertEqual(obs.operation, "SIGN")
        self.assertEqual(obs.primitive, "ASYMMETRIC")
        self.assertEqual(obs.metadata.get("padding"), "PSS")
        self.assertEqual(obs.metadata.get("hash_algorithm"), "SHA256")

        # Verify exact line numbers
        self.assertEqual(match.start_line, 5)
        self.assertEqual(match.end_line, 12)

        # Extract Evidence
        evidence = self.extractor.extract(match, context)
        self.assertEqual(evidence.file_path, "src/crypto_service.py")
        self.assertEqual(evidence.start_line, 5)
        self.assertEqual(evidence.end_line, 12)
        self.assertEqual(evidence.rule_id, "PY-CRYPTO-RSA")

        # Verify the source excerpt matches lines 5 to 12 exactly
        expected_excerpt = (
            "    sig = private_key.sign(\n"
            "        payload,\n"
            "        padding.PSS(\n"
            "            mgf=padding.MGF1(hashes.SHA256()),\n"
            "            salt_length=padding.PSS.MAX_LENGTH,\n"
            "        ),\n"
            "        hashes.SHA256(),\n"
            "    )"
        )
        self.assertEqual(evidence.source_excerpt, expected_excerpt)

    def test_rsa_keygen_detection(self):
        """Detect rsa.generate_private_key call."""
        code = (
            "from cryptography.hazmat.primitives.asymmetric import rsa\n"
            "\n"
            "key = rsa.generate_private_key(\n"
            "    public_exponent=65537,\n"
            "    key_size=4096,\n"
            ")\n"
        )
        context = AnalysisContext.from_source(code, file_path="src/keygen.py")
        tree = ast.parse(code)

        matches = [self.rule.evaluate(node, context) for node in ast.walk(tree) if self.rule.evaluate(node, context)]
        self.assertEqual(len(matches), 1)
        match = matches[0]
        self.assertEqual(match.observation.api, "rsa.generate_private_key")
        self.assertEqual(match.observation.operation, "KEYGEN")
        self.assertEqual(match.observation.metadata.get("key_size"), 4096)
        self.assertEqual(match.observation.metadata.get("public_exponent"), 65537)

    def test_rsa_verify_detection(self):
        """Detect public_key.verify call with PSS padding."""
        code = (
            "public_key.verify(\n"
            "    signature,\n"
            "    data,\n"
            "    padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH),\n"
            "    hashes.SHA256(),\n"
            ")\n"
        )
        context = AnalysisContext.from_source(code, file_path="src/verify.py")
        tree = ast.parse(code)

        matches = [self.rule.evaluate(node, context) for node in ast.walk(tree) if self.rule.evaluate(node, context)]
        self.assertEqual(len(matches), 1)
        match = matches[0]
        self.assertEqual(match.observation.api, "RSAPublicKey.verify")
        self.assertEqual(match.observation.operation, "VERIFY")
        self.assertEqual(match.observation.metadata.get("padding"), "PSS")

    def test_rsa_decrypt_oaep(self):
        """Detect private_key.decrypt with OAEP padding."""
        code = (
            "plaintext = private_key.decrypt(\n"
            "    ciphertext,\n"
            "    padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None),\n"
            ")\n"
        )
        context = AnalysisContext.from_source(code, file_path="src/decrypt.py")
        tree = ast.parse(code)

        matches = [self.rule.evaluate(node, context) for node in ast.walk(tree) if self.rule.evaluate(node, context)]
        self.assertEqual(len(matches), 1)
        match = matches[0]
        self.assertEqual(match.observation.api, "RSAPrivateKey.decrypt")
        self.assertEqual(match.observation.operation, "DECRYPT")
        self.assertEqual(match.observation.metadata.get("padding"), "OAEP")

    def test_reject_unrelated_sign_method(self):
        """Ensure unrelated sign calls (e.g. custom object or unknown) do not falsely trigger RSARule."""
        code = (
            "document.sign(user_id=123, timestamp=456)\n"
            "math.sin(1.57)\n"
        )
        context = AnalysisContext.from_source(code, file_path="src/app.py")
        tree = ast.parse(code)

        matches = [self.rule.evaluate(node, context) for node in ast.walk(tree) if self.rule.evaluate(node, context)]
        self.assertEqual(len(matches), 0)

    def test_evidence_extractor_malformed_encoding(self):
        """Ensure EvidenceExtractor handles malformed bytes without raising UnicodeDecodeError."""
        malformed_bytes = b"def test():\n    return b'\xff\xfe\xfd'\n"
        call_node = ast.Call(
            func=ast.Name(id="test", ctx=ast.Load()),
            args=[],
            keywords=[],
        )
        call_node.lineno = 1
        call_node.end_lineno = 2
        call_node.col_offset = 0

        evidence = self.extractor.extract_from_node(
            node=call_node,
            source=malformed_bytes,
            file_path="src/corrupted.py",
        )
        self.assertEqual(evidence.start_line, 1)
        self.assertEqual(evidence.end_line, 2)
        self.assertIn("def test():", evidence.source_excerpt)


if __name__ == "__main__":
    unittest.main()
