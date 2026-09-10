"""Cross-rule behaviour: no overlap, no name-only detection, stable order."""

import pytest

from app.engine.parser import PythonParser
from app.engine.rules import all_rules, evaluate_file, evaluate_files

ALL_IMPORTS = (
    "from cryptography.hazmat.primitives import hashes\n"
    "from cryptography.hazmat.primitives.asymmetric import ec, ed25519, rsa, x25519\n"
    "from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes\n"
    "from cryptography.hazmat.primitives.ciphers.aead import AESGCM\n"
)


def matches(source: str, path: str = "src/crypto.py"):
    return evaluate_file(PythonParser().parse(source, path))


def test_each_call_node_is_claimed_by_at_most_one_rule_per_algorithm() -> None:
    source = ALL_IMPORTS + (
        "def run(key, peer, data, sig, nonce, iv):\n"
        "    rsa.generate_private_key()\n"
        "    ed25519.Ed25519PrivateKey.generate()\n"
        "    x25519.X25519PrivateKey.generate()\n"
        "    key.sign(data, ec.ECDSA(hashes.SHA256()))\n"
        "    key.exchange(ec.ECDH(), peer)\n"
        "    Cipher(algorithms.AES(key), modes.CBC(iv))\n"
        "    AESGCM(key)\n"
    )

    found = matches(source)
    by_node: dict[int, set[str]] = {}
    for match in found:
        by_node.setdefault(id(match.node), set()).add(match.rule_id)

    assert all(len(rule_ids) == 1 for rule_ids in by_node.values())
    assert {match.algorithm for match in found} == {
        "RSA",
        "Ed25519",
        "X25519",
        "ECDSA",
        "ECDH",
        "AES",
        "SHA-256",
    }


@pytest.mark.parametrize(
    "source",
    [
        # Every one of these names a real algorithm in text only.
        '"""Uses RSA, ECDSA, Ed25519, ECDH, X25519, AES and SHA256."""\nvalue = 1\n',
        "# rsa.generate_private_key, ec.ECDSA, AESGCM, hashes.MD5\nvalue = 1\n",
        "names = ['RSA', 'ECDSA', 'Ed25519', 'ECDH', 'X25519', 'AES', 'SHA256']\n",
        "rsa = ec = ed25519 = x25519 = AES = SHA256 = object()\n",
    ],
)
def test_no_rule_fires_on_names_alone(source: str) -> None:
    assert matches(source) == []


def test_unresolved_receivers_produce_nothing() -> None:
    source = (
        "def run(thing, peer, data, sig, nonce):\n"
        "    thing.sign(data)\n"
        "    thing.verify(sig, data)\n"
        "    thing.encrypt(data)\n"
        "    thing.decrypt(data)\n"
        "    thing.exchange(peer)\n"
        "    thing.generate_private_key()\n"
        "    return thing.encryptor()\n"
    )

    assert matches(source) == []


def test_a_dh_key_generation_is_claimed_by_no_rule() -> None:
    source = (
        "from cryptography.hazmat.primitives.asymmetric import dh\n"
        "def run():\n"
        "    parameters = dh.generate_parameters(generator=2, key_size=2048)\n"
        "    return parameters.generate_private_key()\n"
    )

    assert matches(source) == []


def test_matches_are_ordered_deterministically_across_rules() -> None:
    files = [
        PythonParser().parse(ALL_IMPORTS + "b = hashes.SHA256()\n", "b.py"),
        PythonParser().parse(
            ALL_IMPORTS + "a = rsa.generate_private_key()\nc = hashes.MD5()\n", "a.py"
        ),
    ]

    found = evaluate_files(files)
    assert [match.sort_key for match in found] == sorted(match.sort_key for match in found)
    assert [(m.file_path, m.location.start_line) for m in found] == [
        ("a.py", 5),
        ("a.py", 6),
        ("b.py", 5),
    ]


def test_the_same_file_evaluates_identically_twice() -> None:
    source = ALL_IMPORTS + (
        "def run(key, peer, data, iv):\n"
        "    key.sign(data, ec.ECDSA(hashes.SHA256()))\n"
        "    cipher = Cipher(algorithms.AES(key), modes.CBC(iv))\n"
        "    return cipher.encryptor()\n"
    )

    assert matches(source) == matches(source)


def test_every_registered_rule_reports_nothing_on_empty_source() -> None:
    parsed = PythonParser().parse("value = 1\n", "a.py")

    for rule in all_rules():
        assert evaluate_file(parsed, rules=[rule]) == []


def test_a_file_that_failed_to_parse_yields_nothing_from_any_rule() -> None:
    assert matches("def broken(:\n") == []
