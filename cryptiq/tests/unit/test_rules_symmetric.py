"""AES and hash detection from Python syntax."""

import pytest

from app.engine.parser import PythonParser
from app.engine.rules import CryptoOperation, EvidenceBasis, MatchConfidence, evaluate_file

CIPHERS = "from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes\n"
AEAD = "from cryptography.hazmat.primitives.ciphers.aead import AESGCM\n"
HASHES = "from cryptography.hazmat.primitives import hashes\n"


def matches(source: str, rule_id: str | None = None, path: str = "src/crypto.py"):
    found = evaluate_file(PythonParser().parse(source, path))
    if rule_id is None:
        return found
    return [match for match in found if match.rule_id == rule_id]


def single(source: str, rule_id: str):
    found = matches(source, rule_id)
    assert len(found) == 1, [match.api for match in found]
    return found[0]


# --- AES -------------------------------------------------------------------


def test_naming_the_aes_algorithm_is_a_construction() -> None:
    source = CIPHERS + "def run(key):\n    return algorithms.AES(key)\n"

    match = single(source, "PY-CRYPTO-AES")
    assert match.algorithm == "AES"
    assert match.primitive == "AES"
    assert match.api == "algorithms.AES"
    assert match.operation is CryptoOperation.CONSTRUCTION
    assert match.confidence is MatchConfidence.HIGH
    assert match.evidence_basis is EvidenceBasis.DIRECT_MODULE_API


@pytest.mark.parametrize("class_name", ["AES", "AES128", "AES256"])
def test_every_aes_block_class_is_recognised(class_name: str) -> None:
    source = CIPHERS + f"def run(key):\n    return algorithms.{class_name}(key)\n"

    assert single(source, "PY-CRYPTO-AES").api == f"algorithms.{class_name}"


@pytest.mark.parametrize(
    "class_name", ["AESGCM", "AESGCMSIV", "AESCCM", "AESSIV", "AESOCB3"]
)
def test_every_aead_mode_is_recognised(class_name: str) -> None:
    source = (
        f"from cryptography.hazmat.primitives.ciphers.aead import {class_name}\n"
        f"def run(key):\n    return {class_name}(key)\n"
    )

    match = single(source, "PY-CRYPTO-AES")
    assert match.api == f"aead.{class_name}"
    assert match.operation is CryptoOperation.CONSTRUCTION


def test_a_cipher_context_encrypts_and_decrypts() -> None:
    source = CIPHERS + (
        "def run(key, iv):\n"
        "    cipher = Cipher(algorithms.AES(key), modes.CBC(iv))\n"
        "    cipher.encryptor()\n"
        "    return cipher.decryptor()\n"
    )

    found = matches(source, "PY-CRYPTO-AES")
    assert [(m.api, m.operation.value) for m in found] == [
        ("algorithms.AES", "CONSTRUCTION"),
        ("Cipher.encryptor", "ENCRYPT"),
        ("Cipher.decryptor", "DECRYPT"),
    ]
    assert found[1].confidence is MatchConfidence.MEDIUM


def test_an_aead_context_encrypts_and_decrypts() -> None:
    source = AEAD + (
        "def run(key, nonce, data):\n"
        "    aesgcm = AESGCM(key)\n"
        "    aesgcm.encrypt(nonce, data, None)\n"
        "    return aesgcm.decrypt(nonce, data, None)\n"
    )

    found = matches(source, "PY-CRYPTO-AES")
    assert [(m.api, m.operation.value) for m in found] == [
        ("aead.AESGCM", "CONSTRUCTION"),
        ("AESAEAD.encrypt", "ENCRYPT"),
        ("AESAEAD.decrypt", "DECRYPT"),
    ]


def test_a_cipher_built_from_another_algorithm_is_not_aes() -> None:
    source = CIPHERS + (
        "def run(key, nonce, data):\n"
        "    cipher = Cipher(algorithms.ChaCha20(key, nonce), None)\n"
        "    return cipher.encryptor()\n"
    )

    assert matches(source, "PY-CRYPTO-AES") == []


def test_a_reassigned_cipher_name_is_not_claimed() -> None:
    source = CIPHERS + (
        "def run(key, iv, flag):\n"
        "    cipher = Cipher(algorithms.AES(key), modes.CBC(iv))\n"
        "    if flag:\n"
        "        cipher = load()\n"
        "    return cipher.encryptor()\n"
    )

    apis = [match.api for match in matches(source, "PY-CRYPTO-AES")]
    assert apis == ["algorithms.AES"]


@pytest.mark.parametrize(
    "source",
    [
        "AES = object()\nAES.encrypt(b'')\n",
        "def run(box, data):\n    return box.encrypt(data)\n",
        "def run(box, data):\n    return box.decrypt(data)\n",
        "# algorithms.AES(key) in a comment\nvalue = 1\n",
        "label = 'algorithms.AES'\n",
        "def run(cipher):\n    return cipher.encryptor()\n",
    ],
)
def test_aes_negative_cases(source: str) -> None:
    assert matches(source, "PY-CRYPTO-AES") == []


def test_aes_carries_no_vulnerability_judgement() -> None:
    """The rule records presence, never a verdict about the mode or key size."""
    source = CIPHERS + "def run(key, iv):\n    return Cipher(algorithms.AES(key), modes.ECB())\n"

    match = single(source, "PY-CRYPTO-AES")
    assert match.operation is CryptoOperation.CONSTRUCTION
    assert "ECB" not in match.api


# --- Hashes ----------------------------------------------------------------


@pytest.mark.parametrize(
    ("class_name", "algorithm"),
    [
        ("MD5", "MD5"),
        ("SHA1", "SHA-1"),
        ("SHA224", "SHA-224"),
        ("SHA256", "SHA-256"),
        ("SHA384", "SHA-384"),
        ("SHA512", "SHA-512"),
        ("SHA512_224", "SHA-512/224"),
        ("SHA512_256", "SHA-512/256"),
        ("SHA3_224", "SHA3-224"),
        ("SHA3_256", "SHA3-256"),
        ("SHA3_384", "SHA3-384"),
        ("SHA3_512", "SHA3-512"),
        ("SHAKE128", "SHAKE128"),
        ("SHAKE256", "SHAKE256"),
        ("BLAKE2b", "BLAKE2b"),
        ("BLAKE2s", "BLAKE2s"),
        ("SM3", "SM3"),
    ],
)
def test_every_hash_algorithm_is_named_canonically(class_name: str, algorithm: str) -> None:
    source = HASHES + f"digest = hashes.{class_name}()\n"

    match = single(source, "PY-CRYPTO-HASH")
    assert match.algorithm == algorithm
    assert match.primitive == "HASH"
    assert match.api == f"hashes.{class_name}"
    assert match.operation is CryptoOperation.HASH
    assert match.confidence is MatchConfidence.HIGH


def test_an_aliased_hashes_module_resolves() -> None:
    source = "from cryptography.hazmat.primitives import hashes as h\ndigest = h.SHA256()\n"

    assert single(source, "PY-CRYPTO-HASH").algorithm == "SHA-256"


def test_a_directly_imported_hash_class_resolves() -> None:
    source = "from cryptography.hazmat.primitives.hashes import SHA512\ndigest = SHA512()\n"

    assert single(source, "PY-CRYPTO-HASH").algorithm == "SHA-512"


def test_a_legacy_hash_is_recorded_without_a_verdict() -> None:
    """Cryptiq observes SHA-1; whether it is acceptable here is decided later."""
    source = HASHES + "digest = hashes.SHA1()\n"

    match = single(source, "PY-CRYPTO-HASH")
    assert match.algorithm == "SHA-1"
    assert match.confidence is MatchConfidence.HIGH
    assert match.operation is CryptoOperation.HASH


def test_the_digest_wrapper_is_not_reported_separately() -> None:
    source = HASHES + "def run(data):\n    return hashes.Hash(hashes.SHA256())\n"

    assert [match.api for match in matches(source, "PY-CRYPTO-HASH")] == ["hashes.SHA256"]


@pytest.mark.parametrize(
    "source",
    [
        "SHA256 = object()\nSHA256()\n",
        "def run(library, data):\n    return library.SHA256(data)\n",
        "# hashes.MD5() named in a comment\nvalue = 1\n",
        "label = 'hashes.SHA256'\nother = 'MD5'\n",
        "import hashlib\ndigest = hashlib.sha256()\n",
    ],
)
def test_hash_negative_cases(source: str) -> None:
    assert matches(source, "PY-CRYPTO-HASH") == []


def test_the_hash_and_signature_rules_report_different_calls() -> None:
    source = (
        "from cryptography.hazmat.primitives.asymmetric import ec\n"
        + HASHES
        + "def run(key, data):\n    key.sign(data, ec.ECDSA(hashes.SHA256()))\n"
    )

    found = matches(source)
    assert {match.rule_id for match in found} == {"PY-CRYPTO-ECDSA", "PY-CRYPTO-HASH"}
    assert len({id(match.node) for match in found}) == 2
