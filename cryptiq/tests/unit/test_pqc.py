"""The post-quantum mapping is a fixed table over algorithm and role."""

import pytest

from app.engine.pqc import PqcReviewPath, map_review_path
from app.engine.roles import CryptographicRole

SIGNATURE = CryptographicRole.DIGITAL_SIGNATURE
KEY_ESTABLISHMENT = CryptographicRole.KEY_ESTABLISHMENT
SYMMETRIC = CryptographicRole.SYMMETRIC_ENCRYPTION
HASH = CryptographicRole.HASH


@pytest.mark.parametrize("algorithm", ["RSA", "ECDSA", "Ed25519"])
def test_public_key_signatures_map_to_the_signature_standards(algorithm: str) -> None:
    assessment = map_review_path(algorithm, SIGNATURE)

    assert assessment.review_path is PqcReviewPath.SIGNATURE_MIGRATION
    assert assessment.review_path.value == "ML-DSA / SLH-DSA"
    assert assessment.is_migration_candidate is True
    assert "FIPS 204" in assessment.rationale
    assert "FIPS 205" in assessment.rationale


@pytest.mark.parametrize("algorithm", ["RSA", "ECDH", "X25519"])
def test_key_establishment_maps_to_key_encapsulation(algorithm: str) -> None:
    assessment = map_review_path(algorithm, KEY_ESTABLISHMENT)

    assert assessment.review_path is PqcReviewPath.KEY_ENCAPSULATION_MIGRATION
    assert assessment.review_path.value == "ML-KEM"
    assert assessment.is_migration_candidate is True
    assert "FIPS 203" in assessment.rationale


def test_aes_maps_to_a_key_and_implementation_review() -> None:
    assessment = map_review_path("AES", SYMMETRIC)

    assert assessment.review_path is PqcReviewPath.SYMMETRIC_REVIEW
    assert assessment.review_path.value == "KEY / IMPLEMENTATION REVIEW"
    assert assessment.is_migration_candidate is False
    assert "not broken by Shor" in assessment.rationale


@pytest.mark.parametrize("algorithm", ["SHA-1", "SHA-256", "MD5", "SHA3-512", "BLAKE2b"])
def test_hashes_map_to_a_policy_review(algorithm: str) -> None:
    assessment = map_review_path(algorithm, HASH)

    assert assessment.review_path is PqcReviewPath.HASH_POLICY_REVIEW
    assert assessment.review_path.value == "HASH / POLICY REVIEW"
    assert assessment.is_migration_candidate is False
    assert "does not map to a KEM or a signature" in assessment.rationale


def test_an_unknown_role_falls_through_to_manual_review() -> None:
    assessment = map_review_path("RSA", CryptographicRole.UNKNOWN)

    assert assessment.review_path is PqcReviewPath.MANUAL_REVIEW
    assert assessment.review_path.value == "MANUAL REVIEW"
    assert assessment.is_migration_candidate is False
    assert "not covered by the mapping table" in assessment.rationale


@pytest.mark.parametrize(
    ("algorithm", "role"),
    [
        # An algorithm cannot fill a role it has no mechanism for.
        ("AES", SIGNATURE),
        ("AES", KEY_ESTABLISHMENT),
        ("SHA-256", SIGNATURE),
        ("SHA-256", KEY_ESTABLISHMENT),
        ("RSA", SYMMETRIC),
        ("ECDSA", KEY_ESTABLISHMENT),
        ("X25519", SIGNATURE),
        ("Ed25519", KEY_ESTABLISHMENT),
        ("SOMETHING-ELSE", SIGNATURE),
    ],
)
def test_invalid_combinations_fall_through_to_manual_review(algorithm, role) -> None:
    assessment = map_review_path(algorithm, role)

    assert assessment.review_path is PqcReviewPath.MANUAL_REVIEW
    assert assessment.is_migration_candidate is False


def test_the_algorithm_name_is_matched_case_insensitively() -> None:
    """The table is matched on the upper-cased name; the rationale echoes the
    caller's spelling, so ``Ed25519`` reads as itself rather than ``ED25519``."""
    lower = map_review_path("rsa", SIGNATURE)
    upper = map_review_path("RSA", SIGNATURE)

    assert lower.review_path is upper.review_path
    assert lower.is_migration_candidate == upper.is_migration_candidate
    assert "rsa signatures" in lower.rationale
    assert "RSA signatures" in upper.rationale
    assert map_review_path("ed25519", SIGNATURE).review_path is (
        PqcReviewPath.SIGNATURE_MIGRATION
    )


def test_only_public_key_paths_are_migration_candidates() -> None:
    migrating = {
        PqcReviewPath.SIGNATURE_MIGRATION,
        PqcReviewPath.KEY_ENCAPSULATION_MIGRATION,
    }
    cases = [
        ("RSA", SIGNATURE),
        ("ECDH", KEY_ESTABLISHMENT),
        ("AES", SYMMETRIC),
        ("SHA-1", HASH),
        ("RSA", CryptographicRole.UNKNOWN),
    ]

    for algorithm, role in cases:
        assessment = map_review_path(algorithm, role)
        assert assessment.is_migration_candidate == (assessment.review_path in migrating)


def test_no_rationale_promises_an_automatic_replacement() -> None:
    """The mapping names guidance to read, never a change to apply."""
    forbidden = ("replace with", "replaced by", "swap", "automatically")
    cases = [
        ("RSA", SIGNATURE),
        ("ECDH", KEY_ESTABLISHMENT),
        ("AES", SYMMETRIC),
        ("SHA-1", HASH),
        ("RSA", CryptographicRole.UNKNOWN),
    ]

    for algorithm, role in cases:
        rationale = map_review_path(algorithm, role).rationale.lower()
        assert all(phrase not in rationale for phrase in forbidden)
        assert "review" in rationale


def test_the_mapping_is_deterministic() -> None:
    assert map_review_path("RSA", SIGNATURE) == map_review_path("RSA", SIGNATURE)
