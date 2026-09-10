"""Unit tests for cryptographic migration advisor guardrails.

Guardrails ensure epistemic integrity and prevent category errors:
- Hashing for content-addressing/dedup cannot be mapped to ML-DSA (signature).
- Key establishment cannot be mapped to ML-DSA (signatures do not exchange keys).
- Digital signatures cannot be mapped to ML-KEM (KEMs do not sign data).
- Deterministic facts are immutable and cannot be overridden by model hallucinations.
"""

from app.engine.context.guardrails import enforce_guardrails
from app.engine.context.models import (
    AssessmentConfidence,
    AssessmentDecision,
    ContextualAssessment,
    ContextualRole,
)


def test_guardrails_prevent_hashing_to_mldsa():
    """SHA-256 used for content addressing must never be mapped to ML-DSA."""
    invalid_assessment = ContextualAssessment(
        finding_id="f-sha256",
        fingerprint="sha256-fingerprint",
        assessment=AssessmentDecision.MIGRATE,  # Invalid!
        confidence=AssessmentConfidence.HIGH,
        contextual_role=ContextualRole.CONTENT_ADDRESSING,
        rationale="Migrate this SHA-256 hash to ML-DSA for post-quantum safety.",
        pqc_migration_required=True,  # Invalid!
        migration_candidate="ML-DSA-65",  # Invalid category error!
        alternatives=["ML-DSA-87"],
        engineering_tradeoffs=["High bandwidth overhead"],
    )

    corrected = enforce_guardrails(
        invalid_assessment,
        deterministic_algorithm="SHA-256",
        deterministic_role="CONTENT_ADDRESSING",
    )

    assert corrected.assessment == AssessmentDecision.KEEP
    assert corrected.pqc_migration_required is False
    assert corrected.migration_candidate is None
    assert "ML-DSA" not in (corrected.alternatives or [])
    assert any("category error" in t.lower() for t in corrected.engineering_tradeoffs)


def test_guardrails_prevent_key_establishment_to_mldsa():
    """Key establishment (ECDH) cannot be mapped to signature scheme ML-DSA."""
    invalid_assessment = ContextualAssessment(
        finding_id="f-ecdh",
        fingerprint="ecdh-fingerprint",
        assessment=AssessmentDecision.MIGRATE,
        confidence=AssessmentConfidence.HIGH,
        contextual_role=ContextualRole.KEY_ESTABLISHMENT,
        rationale="Migrate ECDH to ML-DSA.",
        pqc_migration_required=True,
        migration_candidate="ML-DSA-65",  # Wrong primitive type!
    )

    corrected = enforce_guardrails(
        invalid_assessment,
        deterministic_algorithm="ECDH",
        deterministic_role="KEY_ESTABLISHMENT",
    )

    assert corrected.assessment == AssessmentDecision.MIGRATE
    assert corrected.pqc_migration_required is True
    assert corrected.migration_candidate == "ML-KEM-768"


def test_guardrails_prevent_signature_to_mlkem():
    """Digital signature (ECDSA) cannot be mapped to KEM scheme ML-KEM."""
    invalid_assessment = ContextualAssessment(
        finding_id="f-ecdsa",
        fingerprint="ecdsa-fingerprint",
        assessment=AssessmentDecision.MIGRATE,
        confidence=AssessmentConfidence.HIGH,
        contextual_role=ContextualRole.DIGITAL_SIGNATURE,
        rationale="Migrate ECDSA to ML-KEM.",
        pqc_migration_required=True,
        migration_candidate="ML-KEM-768",  # Wrong primitive type!
    )

    corrected = enforce_guardrails(
        invalid_assessment,
        deterministic_algorithm="ECDSA",
        deterministic_role="DIGITAL_SIGNATURE",
    )

    assert corrected.assessment == AssessmentDecision.MIGRATE
    assert corrected.pqc_migration_required is True
    assert corrected.migration_candidate == "ML-DSA-65"


def test_guardrails_preserve_valid_assessment():
    """A valid assessment is passed through intact."""
    valid_assessment = ContextualAssessment(
        finding_id="f-ecdsa-valid",
        fingerprint="ecdsa-fp",
        assessment=AssessmentDecision.MIGRATE,
        confidence=AssessmentConfidence.HIGH,
        contextual_role=ContextualRole.DIGITAL_SIGNATURE,
        rationale="ECDSA firmware signing must migrate to ML-DSA.",
        pqc_migration_required=True,
        migration_candidate="ML-DSA-65",
        alternatives=["SLH-DSA-SHA2-128s"],
        engineering_tradeoffs=["Signature size increases from 64B to ~3.3KB"],
    )

    corrected = enforce_guardrails(
        valid_assessment,
        deterministic_algorithm="ECDSA",
        deterministic_role="DIGITAL_SIGNATURE",
    )

    assert corrected.assessment == AssessmentDecision.MIGRATE
    assert corrected.migration_candidate == "ML-DSA-65"
    assert corrected.pqc_migration_required is True
    assert len(corrected.alternatives) == 1


def test_guardrails_preserve_valid_key_establishment():
    """Valid key establishment to ML-KEM is passed through intact."""
    valid_assessment = ContextualAssessment(
        finding_id="f-ecdh-valid",
        fingerprint="ecdh-fp",
        assessment=AssessmentDecision.MIGRATE,
        confidence=AssessmentConfidence.HIGH,
        contextual_role=ContextualRole.KEY_ESTABLISHMENT,
        rationale="ECDH key agreement migrates to ML-KEM-768.",
        pqc_migration_required=True,
        migration_candidate="ML-KEM-768",
        alternatives=["X25519+ML-KEM-768"],
    )

    corrected = enforce_guardrails(
        valid_assessment,
        deterministic_algorithm="ECDH",
        deterministic_role="KEY_ESTABLISHMENT",
    )

    assert corrected.assessment == AssessmentDecision.MIGRATE
    assert corrected.migration_candidate == "ML-KEM-768"
    assert corrected.pqc_migration_required is True


def test_guardrails_prevent_mac_to_mldsa():
    """HMAC/MAC cannot be mapped to ML-DSA or ML-KEM."""
    invalid_assessment = ContextualAssessment(
        finding_id="f-hmac",
        fingerprint="hmac-fp",
        assessment=AssessmentDecision.MIGRATE,
        confidence=AssessmentConfidence.HIGH,
        contextual_role=ContextualRole.MAC,
        rationale="Migrate HMAC-SHA256 to ML-DSA.",
        pqc_migration_required=True,
        migration_candidate="ML-DSA-65",
        alternatives=["ML-DSA-87"],
    )

    corrected = enforce_guardrails(
        invalid_assessment,
        deterministic_algorithm="HMAC-SHA256",
        deterministic_role="MAC",
    )

    assert corrected.assessment == AssessmentDecision.REVIEW
    assert corrected.pqc_migration_required is False
    assert corrected.migration_candidate is None
    assert "ML-DSA" not in (corrected.alternatives or [])


def test_guardrails_prevent_symmetric_encryption_to_public_key():
    """AES-256-GCM symmetric encryption cannot be replaced with ML-DSA or ML-KEM."""
    invalid_assessment = ContextualAssessment(
        finding_id="f-aes",
        fingerprint="aes-fp",
        assessment=AssessmentDecision.MIGRATE,
        confidence=AssessmentConfidence.HIGH,
        contextual_role=ContextualRole.ENCRYPTION,
        rationale="Migrate AES-GCM to ML-KEM.",
        pqc_migration_required=True,
        migration_candidate="ML-KEM-768",
        alternatives=["ML-DSA-65"],
    )

    corrected = enforce_guardrails(
        invalid_assessment,
        deterministic_algorithm="AES-256-GCM",
        deterministic_role="SYMMETRIC_ENCRYPTION",
    )

    assert corrected.assessment == AssessmentDecision.KEEP
    assert corrected.pqc_migration_required is False
    assert corrected.migration_candidate is None
    assert len(corrected.alternatives) == 0


def test_guardrails_ambiguous_role():
    """Ambiguous or unknown role preserves REVIEW/INSUFFICIENT_CONTEXT without forcing invalid candidates."""
    ambiguous_assessment = ContextualAssessment(
        finding_id="f-unknown",
        fingerprint="unknown-fp",
        assessment=AssessmentDecision.INSUFFICIENT_CONTEXT,
        confidence=AssessmentConfidence.LOW,
        contextual_role=ContextualRole.UNKNOWN,
        rationale="Call site context is insufficient to determine cryptographic role.",
        pqc_migration_required=False,
        migration_candidate=None,
    )

    corrected = enforce_guardrails(
        ambiguous_assessment,
        deterministic_algorithm="GENERIC_CRYPTO",
        deterministic_role="UNKNOWN",
    )

    assert corrected.assessment == AssessmentDecision.INSUFFICIENT_CONTEXT
    assert corrected.migration_candidate is None
    assert corrected.pqc_migration_required is False

