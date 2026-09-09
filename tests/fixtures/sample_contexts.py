"""Shared test fixtures for Cryptiq test suite."""

from cryptiq.compat.interfaces import RuleMatch
from cryptiq.core.enums import ConfidenceLevel, CryptoRole


def make_function_level_finding() -> dict:
    """Fixture for Case 1: crypto call inside a function, no enclosing class."""
    return {
        "id": "f-func-1",
        "repository": "pyca/cryptography",
        "commit_sha": "1f903f5ed2e5e316f345a927555e48535829d8de",
        "file_path": "src/signing.py",
        "start_line": 42,
        "end_line": 42,
        "rule_id": "python.rsa",
        "algorithm": "RSA",
        "api": "RSAPrivateKey.sign",
        "confidence": ConfidenceLevel.CONFIRMED,
        "role": CryptoRole.DIGITAL_SIGNATURE,
        "evidence": {
            "file_path": "src/signing.py",
            "function_name": "sign_certificate",
            "class_name": None,
            "call_site": "private_key.sign(data, padding, algorithm)",
            "confidence": ConfidenceLevel.CONFIRMED,
        },
    }


def make_class_level_finding() -> dict:
    """Fixture for Case 2: crypto call inside a method of a class."""
    return {
        "id": "f-class-1",
        "repository": "pyca/cryptography",
        "commit_sha": "1f903f5ed2e5e316f345a927555e48535829d8de",
        "file_path": "src/certificates/signer.py",
        "start_line": 88,
        "end_line": 88,
        "rule_id": "python.rsa",
        "algorithm": "RSA",
        "api": "RSAPrivateKey.sign",
        "confidence": ConfidenceLevel.CONFIRMED,
        "role": CryptoRole.DIGITAL_SIGNATURE,
        "evidence": {
            "file_path": "src/certificates/signer.py",
            "function_name": "sign_certificate",
            "class_name": "CertificateSigner",
            "call_site": "self.key.sign(data)",
            "confidence": ConfidenceLevel.CONFIRMED,
        },
    }


def make_ambiguous_finding() -> dict:
    """Fixture for Case 3: crypto call at module-level without function or class."""
    return {
        "id": "f-ambig-1",
        "repository": "pyca/cryptography",
        "commit_sha": "1f903f5ed2e5e316f345a927555e48535829d8de",
        "file_path": "src/top_level_init.py",
        "start_line": 15,
        "end_line": 15,
        "rule_id": "python.rsa",
        "algorithm": "RSA",
        "api": "RSAPrivateKey.sign",
        "confidence": ConfidenceLevel.INFERRED,
        "role": CryptoRole.DIGITAL_SIGNATURE,
        "evidence": {
            "file_path": "src/top_level_init.py",
            "function_name": None,
            "class_name": None,
            "call_site": "k.sign(b'test')",
            "confidence": ConfidenceLevel.INFERRED,
        },
    }


def make_missing_context_finding() -> dict:
    """Fixture for Case 4: missing context (e.g. no file, no function)."""
    return {
        "id": "f-missing-1",
        "repository": "pyca/cryptography",
        "commit_sha": "1f903f5ed2e5e316f345a927555e48535829d8de",
        "file_path": "",
        "start_line": 0,
        "end_line": 0,
        "rule_id": "python.rsa",
        "algorithm": "RSA",
        "api": "RSAPrivateKey.sign",
        "confidence": ConfidenceLevel.CONFIRMED,
        "role": CryptoRole.DIGITAL_SIGNATURE,
        "evidence": None,
    }


def make_sample_rule_matches() -> list[RuleMatch]:
    """Return a representative list of parsed RuleMatches across algorithms."""
    return [
        RuleMatch(
            rule_id="python.rsa",
            algorithm="RSA",
            api="RSAPrivateKey.sign",
            file_path="src/certificates/signing.py",
            start_line=54,
            end_line=55,
            confidence=ConfidenceLevel.CONFIRMED,
            role=CryptoRole.DIGITAL_SIGNATURE,
            pqc_guidance="ML-DSA / SLH-DSA signature migration review",
            code_snippet="private_key.sign(data, padding.PSS(), hashes.SHA256())",
            call_site="private_key.sign(...)",
            function_name="sign_certificate",
            class_name="CertificateSigner",
            module_name="certificates.signing",
        ),
        RuleMatch(
            rule_id="python.dh_ecdh",
            algorithm="X25519",
            api="X25519PrivateKey.exchange",
            file_path="src/key_exchange.py",
            start_line=120,
            end_line=120,
            confidence=ConfidenceLevel.CONFIRMED,
            role=CryptoRole.KEY_ESTABLISHMENT,
            pqc_guidance="ML-KEM / hybrid key encapsulation migration review",
            code_snippet="shared_key = private_key.exchange(peer_public_key)",
            call_site="private_key.exchange(...)",
            function_name="establish_session",
            class_name=None,
            module_name="key_exchange",
        ),
        RuleMatch(
            rule_id="python.hash",
            algorithm="SHA-1",
            api="hashlib.sha1",
            file_path="src/legacy_hash.py",
            start_line=30,
            end_line=30,
            confidence=ConfidenceLevel.CONFIRMED,
            role=CryptoRole.HASH,
            pqc_guidance="Separate hash review; classical collision review",
            code_snippet="digest = hashlib.sha1(payload).hexdigest()",
            call_site="hashlib.sha1(...)",
            function_name="checksum",
            class_name=None,
            module_name="legacy_hash",
        ),
    ]
