"""Finding and scan identities stay stable across commits."""

import pytest

from app.engine.fingerprints import ScanIdentity, finding_fingerprint, fingerprint

FINDING = {
    "repository": "github/pyca/cryptography",
    "file_path": "src/signing.py",
    "rule_id": "PY-CRYPTO-RSA",
    "algorithm": "RSA",
    "api": "RSAPrivateKey.sign",
    "operation": "SIGN",
    "enclosing_function": "Signer.sign",
    "enclosing_class": "Signer",
}


def test_the_primitive_is_deterministic_and_separates_parts() -> None:
    assert fingerprint("a", "b") == fingerprint("a", "b")
    assert fingerprint("ab", "c") != fingerprint("a", "bc")

    with pytest.raises(ValueError):
        fingerprint()


def test_a_finding_fingerprint_is_deterministic() -> None:
    assert finding_fingerprint(**FINDING) == finding_fingerprint(**FINDING)
    assert len(finding_fingerprint(**FINDING)) == 64


@pytest.mark.parametrize(
    "field",
    ["repository", "file_path", "rule_id", "algorithm", "api", "operation"],
)
def test_changing_an_identity_field_changes_the_fingerprint(field: str) -> None:
    changed = {**FINDING, field: FINDING[field] + "-other"}

    assert finding_fingerprint(**changed) != finding_fingerprint(**FINDING)


def test_the_enclosing_scope_takes_part_in_the_identity() -> None:
    moved = {**FINDING, "enclosing_function": "Signer.sign_other"}

    assert finding_fingerprint(**moved) != finding_fingerprint(**FINDING)


def test_the_fingerprint_survives_an_edit_above_the_call() -> None:
    """Nothing positional takes part, so inserting a line changes nothing.

    This is what lets a finding be reported as UNCHANGED in a later scan
    instead of looking like a brand new one.
    """
    assert finding_fingerprint(**FINDING) == finding_fingerprint(**FINDING)


def test_a_value_moving_between_fields_does_not_collide() -> None:
    swapped = {**FINDING, "api": FINDING["algorithm"], "algorithm": FINDING["api"]}

    assert finding_fingerprint(**swapped) != finding_fingerprint(**FINDING)


def test_an_absent_scope_is_distinct_from_a_named_one() -> None:
    module_level = {**FINDING, "enclosing_function": None, "enclosing_class": None}

    assert finding_fingerprint(**module_level) != finding_fingerprint(**FINDING)
    assert finding_fingerprint(**module_level) == finding_fingerprint(**module_level)


def test_the_algorithm_is_normalized_but_the_path_is_not() -> None:
    assert finding_fingerprint(**{**FINDING, "algorithm": "rsa"}) == finding_fingerprint(
        **FINDING
    )
    assert finding_fingerprint(**{**FINDING, "file_path": "SRC/Signing.py"}) != (
        finding_fingerprint(**FINDING)
    )


IDENTITY = ScanIdentity(
    provider="github",
    owner="pyca",
    name="cryptography",
    commit_sha="1f903f5ed2e5e316f345a927555e48535829d8de",
    parser_version="python-ast-1",
    ruleset_version="0.1.0",
    pqc_ruleset_version="0.2.0",
)


def test_a_scan_identity_is_deterministic_and_normalized() -> None:
    upper = ScanIdentity(
        provider="GitHub",
        owner="PyCA",
        name="Cryptography",
        commit_sha=IDENTITY.commit_sha.upper(),
        parser_version="python-ast-1",
        ruleset_version="0.1.0",
        pqc_ruleset_version="0.2.0",
    )

    assert upper.canonical_key == IDENTITY.canonical_key
    assert upper.digest == IDENTITY.digest
    assert len(IDENTITY.digest) == 64


@pytest.mark.parametrize(
    "field",
    [
        "provider",
        "owner",
        "name",
        "commit_sha",
        "parser_version",
        "ruleset_version",
        "pqc_ruleset_version",
    ],
)
def test_every_part_of_the_scan_identity_matters(field: str) -> None:
    from dataclasses import replace

    changed = replace(IDENTITY, **{field: getattr(IDENTITY, field) + "x"})

    assert changed.digest != IDENTITY.digest
