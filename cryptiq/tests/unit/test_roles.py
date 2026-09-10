"""Role classification is a fixed table over algorithm and operation."""

from dataclasses import replace

import pytest

from app.engine.parser import PythonParser
from app.engine.roles import CryptographicRole, classify
from app.engine.rules import CryptoOperation, evaluate_file

SOURCE = (
    "from cryptography.hazmat.primitives import hashes\n"
    "from cryptography.hazmat.primitives.asymmetric import ec, ed25519, rsa, x25519\n"
    "from cryptography.hazmat.primitives.ciphers import algorithms\n"
    "def run(key, data, peer, sig):\n"
    "    rsa.generate_private_key()\n"
    "    ed25519.Ed25519PrivateKey.generate()\n"
    "    x25519.X25519PrivateKey.generate()\n"
    "    key.sign(data, ec.ECDSA(hashes.SHA256()))\n"
    "    key.verify(sig, data, ec.ECDSA(hashes.SHA256()))\n"
    "    key.exchange(ec.ECDH(), peer)\n"
    "    algorithms.AES(key)\n"
    "    hashes.SHA1()\n"
)


def matches():
    return evaluate_file(PythonParser().parse(SOURCE, "src/crypto.py"))


def match_for(algorithm: str, operation: str):
    for match in matches():
        if match.algorithm == algorithm and match.operation.value == operation:
            return match
    raise AssertionError(f"no {algorithm} {operation} in the fixture")


def any_match():
    return matches()[0]


@pytest.mark.parametrize(
    ("algorithm", "operation"),
    [("ECDSA", "SIGN"), ("ECDSA", "VERIFY")],
)
def test_ecdsa_signing_is_a_digital_signature(algorithm: str, operation: str) -> None:
    assert classify(match_for(algorithm, operation)).role is CryptographicRole.DIGITAL_SIGNATURE


@pytest.mark.parametrize("operation", [CryptoOperation.SIGN, CryptoOperation.VERIFY])
@pytest.mark.parametrize("algorithm", ["RSA", "ECDSA", "Ed25519"])
def test_every_signature_algorithm_and_operation(algorithm: str, operation) -> None:
    match = replace(any_match(), algorithm=algorithm, operation=operation, primitive=algorithm)

    assert classify(match).role is CryptographicRole.DIGITAL_SIGNATURE


@pytest.mark.parametrize("algorithm", ["ECDH", "X25519"])
def test_key_agreement_is_key_establishment(algorithm: str) -> None:
    match = replace(
        any_match(),
        algorithm=algorithm,
        primitive=algorithm,
        operation=CryptoOperation.KEY_ESTABLISHMENT,
    )

    assert classify(match).role is CryptographicRole.KEY_ESTABLISHMENT


def test_the_real_ecdh_match_is_key_establishment() -> None:
    assert (
        classify(match_for("ECDH", "KEY_ESTABLISHMENT")).role
        is CryptographicRole.KEY_ESTABLISHMENT
    )


def test_aes_is_symmetric_encryption() -> None:
    assert classify(match_for("AES", "CONSTRUCTION")).role is CryptographicRole.SYMMETRIC_ENCRYPTION


@pytest.mark.parametrize(
    "operation",
    [CryptoOperation.ENCRYPT, CryptoOperation.DECRYPT, CryptoOperation.CONSTRUCTION],
)
def test_every_aes_operation_is_symmetric_encryption(operation) -> None:
    match = replace(any_match(), algorithm="AES", primitive="AES", operation=operation)

    assert classify(match).role is CryptographicRole.SYMMETRIC_ENCRYPTION


def test_a_hash_is_a_hash() -> None:
    assert classify(match_for("SHA-1", "HASH")).role is CryptographicRole.HASH


def test_a_hash_is_classified_by_its_primitive_not_its_name() -> None:
    match = replace(any_match(), algorithm="BLAKE2b", primitive="HASH", operation=CryptoOperation.HASH)

    assert classify(match).role is CryptographicRole.HASH


def test_rsa_encryption_is_key_transport() -> None:
    """RSA encrypt wraps a symmetric key, which is what ML-KEM replaces."""
    match = replace(
        any_match(), algorithm="RSA", primitive="RSA", operation=CryptoOperation.ENCRYPT
    )

    assessment = classify(match)
    assert assessment.role is CryptographicRole.KEY_ESTABLISHMENT
    assert "transports a key" in assessment.rationale


def test_rsa_key_generation_has_no_established_role() -> None:
    """An RSA key can sign or transport, so generating one settles nothing."""
    assessment = classify(match_for("RSA", "KEY_GENERATION"))

    assert assessment.role is CryptographicRole.UNKNOWN
    assert "does not establish the role" in assessment.rationale


def test_ed25519_key_generation_can_only_be_a_signature() -> None:
    assessment = classify(match_for("Ed25519", "KEY_GENERATION"))

    assert assessment.role is CryptographicRole.DIGITAL_SIGNATURE
    assert "only be used for signatures" in assessment.rationale


def test_x25519_key_generation_can_only_be_key_agreement() -> None:
    assessment = classify(match_for("X25519", "KEY_GENERATION"))

    assert assessment.role is CryptographicRole.KEY_ESTABLISHMENT
    assert "only be used for key agreement" in assessment.rationale


def test_an_unrecognised_algorithm_is_unknown() -> None:
    match = replace(
        any_match(),
        algorithm="SOMETHING-ELSE",
        primitive="SOMETHING-ELSE",
        operation=CryptoOperation.KEY_GENERATION,
    )

    assert classify(match).role is CryptographicRole.UNKNOWN


def test_every_classification_carries_a_rationale() -> None:
    for match in matches():
        assessment = classify(match)
        assert assessment.rationale
        assert assessment.rationale.endswith(".")


def test_classification_is_deterministic() -> None:
    for match in matches():
        assert classify(match) == classify(match)


def test_nothing_produces_the_protocol_role_yet() -> None:
    """PROTOCOL is in the vocabulary but no rule recognises a protocol."""
    assert CryptographicRole.PROTOCOL in set(CryptographicRole)
    assert all(classify(match).role is not CryptographicRole.PROTOCOL for match in matches())


def test_the_engine_and_database_vocabularies_agree() -> None:
    from app.db.models.enums import CryptographicRole as StoredRole

    assert {role.value for role in CryptographicRole} == {role.value for role in StoredRole}
