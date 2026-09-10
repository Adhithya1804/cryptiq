"""ECDSA, Ed25519, ECDH and X25519 detection from Python syntax."""

import pytest

from app.engine.parser import PythonParser
from app.engine.rules import CryptoOperation, EvidenceBasis, MatchConfidence, evaluate_file

EC = "from cryptography.hazmat.primitives.asymmetric import ec\n"
HASHES = "from cryptography.hazmat.primitives import hashes\n"
ED = "from cryptography.hazmat.primitives.asymmetric import ed25519\n"
ED_CLASS = (
    "from cryptography.hazmat.primitives.asymmetric.ed25519 import "
    "Ed25519PrivateKey, Ed25519PublicKey\n"
)
X = "from cryptography.hazmat.primitives.asymmetric import x25519\n"
X_CLASS = (
    "from cryptography.hazmat.primitives.asymmetric.x25519 import "
    "X25519PrivateKey, X25519PublicKey\n"
)


def matches(source: str, rule_id: str | None = None, path: str = "src/keys.py"):
    found = evaluate_file(PythonParser().parse(source, path))
    if rule_id is None:
        return found
    return [match for match in found if match.rule_id == rule_id]


def single(source: str, rule_id: str):
    found = matches(source, rule_id)
    assert len(found) == 1, [match.api for match in found]
    return found[0]


# --- ECDSA -----------------------------------------------------------------


def test_ecdsa_signing_is_proved_by_the_marker_argument() -> None:
    source = EC + HASHES + "def run(key, data):\n    key.sign(data, ec.ECDSA(hashes.SHA256()))\n"

    match = single(source, "PY-CRYPTO-ECDSA")
    assert match.algorithm == "ECDSA"
    assert match.primitive == "ECDSA"
    assert match.api == "ECDSA.sign"
    assert match.operation is CryptoOperation.SIGN
    assert match.confidence is MatchConfidence.HIGH
    assert match.evidence_basis is EvidenceBasis.DIRECT_MODULE_API


def test_ecdsa_verification_is_recognised() -> None:
    source = EC + HASHES + (
        "def run(key, sig, data):\n    key.verify(sig, data, ec.ECDSA(hashes.SHA256()))\n"
    )

    match = single(source, "PY-CRYPTO-ECDSA")
    assert match.api == "ECDSA.verify"
    assert match.operation is CryptoOperation.VERIFY


def test_an_ecdsa_marker_held_in_a_local_name_is_medium_confidence() -> None:
    source = EC + HASHES + (
        "def run(key, data):\n"
        "    algorithm = ec.ECDSA(hashes.SHA256())\n"
        "    key.sign(data, algorithm)\n"
    )

    match = single(source, "PY-CRYPTO-ECDSA")
    assert match.confidence is MatchConfidence.MEDIUM
    assert match.evidence_basis is EvidenceBasis.CONSTRUCTOR_ASSIGNMENT


def test_an_ambiguous_marker_name_is_not_claimed() -> None:
    source = EC + HASHES + (
        "def run(key, data, flag):\n"
        "    algorithm = ec.ECDSA(hashes.SHA256())\n"
        "    if flag:\n"
        "        algorithm = load()\n"
        "    key.sign(data, algorithm)\n"
    )

    assert matches(source, "PY-CRYPTO-ECDSA") == []


def test_the_ecdsa_marker_survives_a_chained_receiver() -> None:
    source = EC + HASHES + (
        "def run(box, data):\n    box.key().sign(data, ec.ECDSA(hashes.SHA256()))\n"
    )

    assert single(source, "PY-CRYPTO-ECDSA").api == "ECDSA.sign"


@pytest.mark.parametrize(
    "body",
    [
        "def run(key, data):\n    key.sign(data)\n",
        "def run(key, curve):\n    return ec.generate_private_key(ec.SECP256R1())\n",
        "def run():\n    return ec.SECP384R1()\n",
        "def run(builder, data):\n    return builder.sign(data, 'ECDSA')\n",
        "def run(key, data):\n    return key.verify(data)\n",
    ],
)
def test_generic_ec_use_is_not_ecdsa(body: str) -> None:
    assert matches(EC + HASHES + body, "PY-CRYPTO-ECDSA") == []


# --- ECDH ------------------------------------------------------------------


def test_ecdh_is_proved_by_the_marker_argument() -> None:
    source = EC + "def run(key, peer):\n    return key.exchange(ec.ECDH(), peer)\n"

    match = single(source, "PY-CRYPTO-ECDH")
    assert match.algorithm == "ECDH"
    assert match.api == "ECDH.exchange"
    assert match.operation is CryptoOperation.KEY_ESTABLISHMENT
    assert match.confidence is MatchConfidence.HIGH


def test_an_ecdh_marker_in_a_local_name_is_medium_confidence() -> None:
    source = EC + (
        "def run(key, peer):\n    algorithm = ec.ECDH()\n    return key.exchange(algorithm, peer)\n"
    )

    assert single(source, "PY-CRYPTO-ECDH").confidence is MatchConfidence.MEDIUM


@pytest.mark.parametrize(
    "body",
    [
        "def run(session, peer):\n    return session.exchange(peer)\n",
        "def run(book, peer):\n    return book.exchange(peer)\n",
        "def run():\n    return ec.SECP256R1()\n",
    ],
)
def test_a_generic_exchange_is_not_ecdh(body: str) -> None:
    assert matches(EC + body, "PY-CRYPTO-ECDH") == []


def test_ecdsa_signing_is_never_reported_as_ecdh() -> None:
    source = EC + HASHES + "def run(key, data):\n    key.sign(data, ec.ECDSA(hashes.SHA256()))\n"

    assert matches(source, "PY-CRYPTO-ECDH") == []
    assert matches(source, "PY-CRYPTO-ECDSA")


def test_key_agreement_is_never_reported_as_ecdsa() -> None:
    source = EC + "def run(key, peer):\n    return key.exchange(ec.ECDH(), peer)\n"

    assert matches(source, "PY-CRYPTO-ECDSA") == []
    assert matches(source, "PY-CRYPTO-ECDH")


# --- Ed25519 ---------------------------------------------------------------


def test_ed25519_generation_is_high_confidence() -> None:
    source = ED + "key = ed25519.Ed25519PrivateKey.generate()\n"

    match = single(source, "PY-CRYPTO-ED25519")
    assert match.algorithm == "Ed25519"
    assert match.api == "Ed25519PrivateKey.generate"
    assert match.operation is CryptoOperation.KEY_GENERATION
    assert match.confidence is MatchConfidence.HIGH


def test_an_aliased_ed25519_module_resolves() -> None:
    source = (
        "from cryptography.hazmat.primitives.asymmetric import ed25519 as e\n"
        "key = e.Ed25519PrivateKey.generate()\n"
    )

    assert single(source, "PY-CRYPTO-ED25519").api == "Ed25519PrivateKey.generate"


def test_an_ed25519_annotation_establishes_the_receiver() -> None:
    source = ED_CLASS + "def run(key: Ed25519PrivateKey, data):\n    return key.sign(data)\n"

    match = single(source, "PY-CRYPTO-ED25519")
    assert match.api == "Ed25519PrivateKey.sign"
    assert match.confidence is MatchConfidence.HIGH
    assert match.evidence_basis is EvidenceBasis.CLASS_ANNOTATION


def test_an_ed25519_public_key_verifies() -> None:
    source = ED_CLASS + (
        "def run(key: Ed25519PublicKey, sig, data):\n    return key.verify(sig, data)\n"
    )

    assert single(source, "PY-CRYPTO-ED25519").operation is CryptoOperation.VERIFY


def test_an_ed25519_key_from_a_generator_is_medium_confidence() -> None:
    source = ED_CLASS + (
        "def run(data):\n    key = Ed25519PrivateKey.generate()\n    return key.sign(data)\n"
    )

    signing = [m for m in matches(source, "PY-CRYPTO-ED25519") if m.operation.value == "SIGN"]
    assert signing[0].confidence is MatchConfidence.MEDIUM


def test_loading_a_key_is_not_generating_one() -> None:
    source = ED_CLASS + "key = Ed25519PrivateKey.from_private_bytes(b'')\n"

    assert matches(source, "PY-CRYPTO-ED25519") == []


def test_a_derived_ed25519_public_key_can_verify() -> None:
    source = ED_CLASS + (
        "def run(sig, data):\n"
        "    private = Ed25519PrivateKey.generate()\n"
        "    public = private.public_key()\n"
        "    return public.verify(sig, data)\n"
    )

    apis = [match.api for match in matches(source, "PY-CRYPTO-ED25519")]
    assert apis == ["Ed25519PrivateKey.generate", "Ed25519PublicKey.verify"]


@pytest.mark.parametrize(
    "source",
    [
        "def run(key, data):\n    return key.sign(data)\n",
        (
            "class Ed25519PrivateKey:\n    def sign(self, d):\n        return d\n\n"
            "Ed25519PrivateKey().sign(b'')\n"
        ),
        "# ed25519.Ed25519PrivateKey.generate() in a comment\nvalue = 1\n",
        "label = 'Ed25519PrivateKey.generate'\n",
        "Ed25519PrivateKey = object()\n",
    ],
)
def test_ed25519_negative_cases(source: str) -> None:
    assert matches(source, "PY-CRYPTO-ED25519") == []


def test_a_wrong_half_ed25519_call_is_not_reported() -> None:
    source = ED_CLASS + (
        "def run(key: Ed25519PublicKey, data):\n    return key.sign(data)\n"
    )

    assert matches(source, "PY-CRYPTO-ED25519") == []


# --- X25519 ----------------------------------------------------------------


def test_x25519_generation_is_high_confidence() -> None:
    source = X + "key = x25519.X25519PrivateKey.generate()\n"

    match = single(source, "PY-CRYPTO-X25519")
    assert match.algorithm == "X25519"
    assert match.api == "X25519PrivateKey.generate"
    assert match.operation is CryptoOperation.KEY_GENERATION


def test_a_fully_qualified_x25519_import_resolves() -> None:
    source = (
        "import cryptography.hazmat.primitives.asymmetric.x25519 as x\n"
        "key = x.X25519PrivateKey.generate()\n"
    )

    assert single(source, "PY-CRYPTO-X25519").api == "X25519PrivateKey.generate"


def test_x25519_exchange_needs_an_established_private_key() -> None:
    source = X_CLASS + (
        "def run(key: X25519PrivateKey, peer):\n    return key.exchange(peer)\n"
    )

    match = single(source, "PY-CRYPTO-X25519")
    assert match.api == "X25519PrivateKey.exchange"
    assert match.operation is CryptoOperation.KEY_ESTABLISHMENT
    assert match.confidence is MatchConfidence.HIGH


def test_an_x25519_public_key_does_not_exchange() -> None:
    source = X_CLASS + "def run(key: X25519PublicKey, peer):\n    return key.exchange(peer)\n"

    assert matches(source, "PY-CRYPTO-X25519") == []


@pytest.mark.parametrize(
    "source",
    [
        "def run(session, peer):\n    return session.exchange(peer)\n",
        "def run(book, peer):\n    return book.exchange(peer)\n",
        "X25519PrivateKey = object()\nX25519PrivateKey.generate()\n",
        "# x25519.X25519PrivateKey.generate() mentioned here\nvalue = 1\n",
    ],
)
def test_x25519_negative_cases(source: str) -> None:
    assert matches(source, "PY-CRYPTO-X25519") == []


def test_x25519_and_ecdh_do_not_both_claim_one_call() -> None:
    source = X_CLASS + "def run(key: X25519PrivateKey, peer):\n    return key.exchange(peer)\n"

    rule_ids = {match.rule_id for match in matches(source)}
    assert rule_ids == {"PY-CRYPTO-X25519"}
