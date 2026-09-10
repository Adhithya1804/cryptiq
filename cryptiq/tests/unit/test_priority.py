"""Migration review priority is a fixed table, not a judgement call."""

from dataclasses import replace

import pytest

from app.engine.impact import analyze
from app.engine.parser import PythonParser
from app.engine.priority import ReviewPriority, score
from app.engine.rules import CryptoOperation, MatchConfidence, evaluate_file

IMPORT = "from cryptography.hazmat.primitives.asymmetric import rsa\n"


def rsa_match(source: str | None = None):
    source = source or IMPORT + "key = rsa.generate_private_key()\n"
    parsed = PythonParser().parse(source, "src/signing.py")
    return evaluate_file(parsed)[0], parsed


NESTED_SOURCE = (
    IMPORT
    + "class Signer:\n"
    + "    def sign(self, key: rsa.RSAPrivateKey, payload):\n"
    + "        return key.sign(payload)\n"
)


def test_a_high_confidence_rsa_key_generation_is_high_priority() -> None:
    match, parsed = rsa_match()

    result = score(match, analyze(match, parsed.module_path))

    assert result.level is ReviewPriority.HIGH
    assert result.score == 30 + 40 + 30
    assert any("Shor" in reason for reason in result.reasons)
    assert any("KEY_GENERATION" in reason for reason in result.reasons)


def test_a_narrow_graph_earns_no_impact_bonus() -> None:
    match, parsed = rsa_match()
    impact = analyze(match, parsed.module_path)

    assert impact.node_count == 4
    assert score(match, impact).score == score(match, None).score


def test_a_broad_graph_earns_the_impact_bonus() -> None:
    match, parsed = rsa_match(NESTED_SOURCE)
    impact = analyze(match, parsed.module_path)

    assert impact.node_count == 6
    assert score(match, impact).score - score(match, None).score == 10
    assert any("Blast radius" in reason for reason in score(match, impact).reasons)


def test_lower_confidence_lowers_the_score() -> None:
    match, _ = rsa_match()

    high = score(replace(match, confidence=MatchConfidence.HIGH))
    medium = score(replace(match, confidence=MatchConfidence.MEDIUM))
    low = score(replace(match, confidence=MatchConfidence.LOW))

    assert high.score > medium.score > low.score
    assert high.level is ReviewPriority.HIGH
    assert low.level is ReviewPriority.MEDIUM


@pytest.mark.parametrize(
    ("algorithm", "expected_points"),
    [
        ("RSA", 40),
        ("ECDSA", 40),
        ("X25519", 40),
        ("MD5", 25),
        ("SHA-1", 25),
        ("SHA-256", 15),
        ("AES", 15),
        ("CHACHA20", 15),
        ("SOMETHING-ELSE", 10),
    ],
)
def test_the_algorithm_tables_decide_the_family_points(
    algorithm: str, expected_points: int
) -> None:
    match, _ = rsa_match()
    result = score(replace(match, algorithm=algorithm, operation=CryptoOperation.SIGN))

    assert result.score == 30 + expected_points + 30


def test_a_post_quantum_primitive_is_not_a_migration_candidate() -> None:
    match, _ = rsa_match()

    result = score(replace(match, algorithm="ML-KEM"))

    assert result.level is ReviewPriority.LOW
    assert any("post-quantum" in reason for reason in result.reasons)
    assert not any("Shor" in reason for reason in result.reasons)


def test_the_algorithm_name_is_matched_case_insensitively() -> None:
    match, _ = rsa_match()

    assert score(replace(match, algorithm="rsa")).score == score(match).score


@pytest.mark.parametrize("operation", list(CryptoOperation))
def test_every_operation_contributes_points(operation: CryptoOperation) -> None:
    from app.engine.priority.scorer import OPERATION_POINTS

    match, _ = rsa_match()

    result = score(replace(match, operation=operation))

    assert result.score == 30 + 40 + OPERATION_POINTS[operation]
    assert any(operation.value in reason for reason in result.reasons)


def test_key_operations_outrank_inventory_operations() -> None:
    """Naming a primitive is inventory; using a key is what gets reviewed."""
    from app.engine.priority.scorer import OPERATION_POINTS

    for key_operation in (
        CryptoOperation.SIGN,
        CryptoOperation.VERIFY,
        CryptoOperation.KEY_GENERATION,
        CryptoOperation.KEY_ESTABLISHMENT,
    ):
        assert OPERATION_POINTS[key_operation] > OPERATION_POINTS[CryptoOperation.CONSTRUCTION]
        assert OPERATION_POINTS[key_operation] > OPERATION_POINTS[CryptoOperation.HASH]


def test_every_reason_is_a_fixed_string_not_generated_prose() -> None:
    match, parsed = rsa_match()

    first = score(match, analyze(match, parsed.module_path))
    second = score(match, analyze(match, parsed.module_path))

    assert first == second
    assert first.reasons


def test_the_bands_follow_the_documented_thresholds() -> None:
    from app.engine.priority.scorer import HIGH_THRESHOLD, MEDIUM_THRESHOLD, _band

    assert _band(HIGH_THRESHOLD) is ReviewPriority.HIGH
    assert _band(HIGH_THRESHOLD - 1) is ReviewPriority.MEDIUM
    assert _band(MEDIUM_THRESHOLD) is ReviewPriority.MEDIUM
    assert _band(MEDIUM_THRESHOLD - 1) is ReviewPriority.LOW


def test_the_engine_bands_are_a_subset_of_the_persisted_vocabulary() -> None:
    from app.db.models.enums import ReviewPriority as StoredPriority

    assert {level.value for level in ReviewPriority} == {
        level.value for level in StoredPriority
    }


# --- role as an input -------------------------------------------------------


def test_the_role_appears_in_the_reasons() -> None:
    from app.engine.roles import CryptographicRole

    match, _ = rsa_match()

    result = score(match, None, CryptographicRole.KEY_ESTABLISHMENT)

    assert any("KEY_ESTABLISHMENT" in reason for reason in result.reasons)


def test_an_unknown_role_adds_no_reason() -> None:
    from app.engine.roles import CryptographicRole

    match, _ = rsa_match()

    with_unknown = score(match, None, CryptographicRole.UNKNOWN)
    without = score(match, None)

    assert with_unknown.score == without.score
    assert not any("Classified as" in reason for reason in with_unknown.reasons)


def test_key_transport_scores_as_a_key_operation() -> None:
    """RSA encrypt is spelled ENCRYPT but is key establishment."""
    from app.engine.roles import CryptographicRole

    match, _ = rsa_match()
    encrypting = replace(match, operation=CryptoOperation.ENCRYPT)

    plain = score(encrypting, None)
    as_key_establishment = score(encrypting, None, CryptographicRole.KEY_ESTABLISHMENT)

    assert plain.score == 30 + 40 + 25
    assert as_key_establishment.score == 30 + 40 + 30


def test_a_role_never_raises_an_operation_that_already_scores_higher() -> None:
    from app.engine.roles import CryptographicRole

    match, _ = rsa_match()
    signing = replace(match, operation=CryptoOperation.SIGN)

    assert score(signing, None, CryptographicRole.DIGITAL_SIGNATURE).score == score(
        signing, None
    ).score


def test_a_role_alone_does_not_decide_the_priority() -> None:
    """A hash classified HASH still scores by its algorithm family."""
    from app.engine.roles import CryptographicRole

    match, _ = rsa_match()
    hashing = replace(
        match, algorithm="SHA-256", primitive="HASH", operation=CryptoOperation.HASH
    )

    result = score(hashing, None, CryptographicRole.HASH)
    signing = score(replace(match, operation=CryptoOperation.SIGN), None,
                    CryptographicRole.DIGITAL_SIGNATURE)

    assert result.score == 30 + 15 + 10
    assert result.level is ReviewPriority.MEDIUM
    assert result.score < signing.score
    assert not any("Shor" in reason for reason in result.reasons)
