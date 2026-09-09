import ast
import unittest

from app.engine.models import AnalysisContext
from app.engine.rules import (
    AESRule,
    ECDHRule,
    ECDSARule,
    Ed25519Rule,
    HashRule,
    RSARule,
    RuleRegistry,
    X25519Rule,
)


class TestPhase6Rules(unittest.TestCase):

    def setUp(self):
        self.registry = RuleRegistry.default_registry()

    def test_registry_initialization(self):
        """Verify registry holds all 7 Phase 6 rules."""
        rules = self.registry.list_rules()
        self.assertEqual(len(rules), 7)
        rule_ids = {r.rule_id for r in rules}
        expected_ids = {
            "PY-CRYPTO-RSA",
            "PY-CRYPTO-ECDSA",
            "PY-CRYPTO-ED25519",
            "PY-CRYPTO-ECDH",
            "PY-CRYPTO-X25519",
            "PY-CRYPTO-AES",
            "PY-CRYPTO-HASH",
        }
        self.assertEqual(rule_ids, expected_ids)

    def test_acceptance_criteria_x25519_chained_exchange(self):
        """
        Acceptance Criteria:
        Passing a parsed file containing X25519PrivateKey.generate().exchange()
        yields a valid RuleMatch for X25519.
        """
        code = (
            "from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey\n"
            "\n"
            "def perform_exchange(peer_key):\n"
            "    shared = X25519PrivateKey.generate().exchange(peer_key)\n"
            "    return shared\n"
        )
        context = AnalysisContext.from_source(code, file_path="src/kex.py")
        tree = ast.parse(code)

        matches = self.registry.evaluate_tree(tree, context)
        x25519_matches = [m for m in matches if m.rule_id == "PY-CRYPTO-X25519"]

        # Expect both .generate() and .exchange() matches on X25519
        self.assertGreaterEqual(len(x25519_matches), 1)

        exchange_matches = [m for m in x25519_matches if m.observation.api == "X25519PrivateKey.exchange"]
        self.assertEqual(len(exchange_matches), 1)

        match = exchange_matches[0]
        self.assertEqual(match.observation.algorithm, "X25519")
        self.assertEqual(match.observation.library, "cryptography")
        self.assertEqual(match.observation.operation, "KEY_EXCHANGE")
        self.assertEqual(match.observation.primitive, "ASYMMETRIC")
        self.assertEqual(match.start_line, 4)

    def test_ecdsa_sign_and_verify(self):
        """Verify ECDSA signing with ec.ECDSA(...) and verification."""
        code = (
            "from cryptography.hazmat.primitives.asymmetric import ec\n"
            "from cryptography.hazmat.primitives import hashes\n"
            "\n"
            "def sign_and_verify(private_key, public_key, data):\n"
            "    sig = private_key.sign(data, ec.ECDSA(hashes.SHA256()))\n"
            "    public_key.verify(sig, data, ec.ECDSA(hashes.SHA256()))\n"
            "    return sig\n"
        )
        context = AnalysisContext.from_source(code, file_path="src/ecdsa_flow.py")
        tree = ast.parse(code)

        matches = self.registry.evaluate_tree(tree, context)
        ecdsa_matches = [m for m in matches if m.rule_id == "PY-CRYPTO-ECDSA"]
        self.assertEqual(len(ecdsa_matches), 2)

        sign_match = next(m for m in ecdsa_matches if m.observation.operation == "SIGN")
        self.assertEqual(sign_match.observation.api, "EllipticCurvePrivateKey.sign")
        self.assertEqual(sign_match.observation.metadata.get("hash_algorithm"), "SHA256")

        verify_match = next(m for m in ecdsa_matches if m.observation.operation == "VERIFY")
        self.assertEqual(verify_match.observation.api, "EllipticCurvePublicKey.verify")
        self.assertEqual(verify_match.observation.metadata.get("hash_algorithm"), "SHA256")

    def test_ed25519_lifecycle(self):
        """Verify Ed25519 key generation, signing, and verification."""
        code = (
            "from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey\n"
            "\n"
            "key = Ed25519PrivateKey.generate()\n"
            "sig = key.sign(b'hello')\n"
            "pub = key.public_key()\n"
            "pub.verify(sig, b'hello')\n"
        )
        context = AnalysisContext.from_source(code, file_path="src/ed25519_ops.py")
        tree = ast.parse(code)

        matches = self.registry.evaluate_tree(tree, context)
        ed_matches = [m for m in matches if m.rule_id == "PY-CRYPTO-ED25519"]
        self.assertGreaterEqual(len(ed_matches), 3)

        operations = {m.observation.operation for m in ed_matches}
        self.assertTrue({"KEYGEN", "SIGN", "VERIFY"}.issubset(operations))

    def test_ecdh_key_exchange(self):
        """Verify ECDH .exchange(ec.ECDH(), peer_key) detection."""
        code = (
            "from cryptography.hazmat.primitives.asymmetric import ec\n"
            "\n"
            "shared_secret = private_key.exchange(ec.ECDH(), peer_public_key)\n"
        )
        context = AnalysisContext.from_source(code, file_path="src/ecdh_kex.py")
        tree = ast.parse(code)

        matches = self.registry.evaluate_tree(tree, context)
        ecdh_matches = [m for m in matches if m.rule_id == "PY-CRYPTO-ECDH"]
        self.assertEqual(len(ecdh_matches), 1)
        self.assertEqual(ecdh_matches[0].observation.api, "ECDH.exchange")
        self.assertEqual(ecdh_matches[0].observation.operation, "KEY_EXCHANGE")

    def test_aes_symmetric_detection(self):
        """Verify AES cipher detection without vulnerability flags."""
        code = (
            "from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes\n"
            "\n"
            "cipher = Cipher(algorithms.AES(key), modes.CBC(iv))\n"
        )
        context = AnalysisContext.from_source(code, file_path="src/encrypt.py")
        tree = ast.parse(code)

        matches = self.registry.evaluate_tree(tree, context)
        aes_matches = [m for m in matches if m.rule_id == "PY-CRYPTO-AES"]
        self.assertEqual(len(aes_matches), 1)

        match = aes_matches[0]
        self.assertEqual(match.observation.algorithm, "AES")
        self.assertEqual(match.observation.api, "algorithms.AES")
        self.assertEqual(match.observation.operation, "SYMMETRIC_ENCRYPTION")
        self.assertEqual(match.observation.primitive, "SYMMETRIC")
        self.assertEqual(match.observation.metadata.get("mode"), "CBC")
        # Ensure no hallucinated vulnerability fields
        self.assertNotIn("is_vulnerable", match.observation.metadata)

    def test_hashes_detection_cryptography_and_hashlib(self):
        """Verify HashRule captures SHA256, MD5, and hashlib.new without vulnerability judgments."""
        code = (
            "import hashlib\n"
            "from cryptography.hazmat.primitives import hashes\n"
            "\n"
            "h1 = hashes.SHA256()\n"
            "h2 = hashlib.md5(b'test')\n"
            "h3 = hashlib.new('sha512')\n"
        )
        context = AnalysisContext.from_source(code, file_path="src/hashing.py")
        tree = ast.parse(code)

        matches = self.registry.evaluate_tree(tree, context)
        hash_matches = [m for m in matches if m.rule_id == "PY-CRYPTO-HASH"]
        self.assertEqual(len(hash_matches), 3)

        algos = {m.observation.algorithm for m in hash_matches}
        self.assertEqual(algos, {"SHA-256", "MD5", "SHA-512"})

        for m in hash_matches:
            self.assertEqual(m.observation.operation, "HASH")
            self.assertEqual(m.observation.primitive, "HASH")
            self.assertNotIn("is_vulnerable", m.observation.metadata)

    def test_false_positive_rejection(self):
        """Ensure generic non-crypto methods (.sign, .exchange, math.sin) are rejected."""
        code = (
            "document.sign(user_id=1)\n"
            "currency_exchange.exchange(amount=100, currency='EUR')\n"
            "import math\n"
            "val = math.sin(0.5)\n"
        )
        context = AnalysisContext.from_source(code, file_path="src/unrelated.py")
        tree = ast.parse(code)

        matches = self.registry.evaluate_tree(tree, context)
        self.assertEqual(len(matches), 0)


if __name__ == "__main__":
    unittest.main()
