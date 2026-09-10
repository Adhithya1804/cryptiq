"""Guardrails enforcing cryptographic semantic consistency.

Ensures that LLM or heuristic recommendations do not make category errors:
- SHA-256 / Hashing cannot be replaced with ML-DSA (digital signature) or ML-KEM (KEM).
- Key establishment cannot be mapped to ML-DSA (signature).
- Digital signatures cannot be mapped to ML-KEM (encapsulation).
"""

from __future__ import annotations

import logging
from dataclasses import replace

from app.engine.context.models import (
    AssessmentDecision,
    ContextualAssessment,
    ContextualRole,
)

logger = logging.getLogger(__name__)

SIGNATURE_SCHEMES = frozenset(
    {"ML-DSA", "ML-DSA-44", "ML-DSA-65", "ML-DSA-87", "SLH-DSA", "FIPS 204", "FIPS 205"}
)
KEM_SCHEMES = frozenset(
    {"ML-KEM", "ML-KEM-512", "ML-KEM-768", "ML-KEM-1024", "FIPS 203"}
)
HASH_ROLES = frozenset(
    {
        ContextualRole.CONTENT_ADDRESSING,
        ContextualRole.DATA_INTEGRITY,
        ContextualRole.HASHING,
        ContextualRole.PASSWORD_DERIVATION,
        ContextualRole.MAC,
    }
)


def _matches_family(candidate: str | None, family: frozenset[str]) -> bool:
    if not candidate:
        return False
    upper = candidate.strip().upper()
    return any(f in upper for f in family)


def enforce_guardrails(
    assessment: ContextualAssessment,
    deterministic_algorithm: str,
    deterministic_role: str,
) -> ContextualAssessment:
    """Validate and correct any semantic category errors in a contextual assessment."""
    role = assessment.contextual_role
    candidate = assessment.migration_candidate
    decision = assessment.assessment
    rationale = assessment.rationale
    tradeoffs = list(assessment.engineering_tradeoffs)
    limitations = list(assessment.limitations)
    migration_required = assessment.pqc_migration_required

    # Invariant 1: Hash functions must NEVER be mapped to ML-DSA or ML-KEM
    if role in HASH_ROLES or deterministic_role.upper() == "HASH":
        if _matches_family(candidate, SIGNATURE_SCHEMES) or _matches_family(candidate, KEM_SCHEMES):
            logger.warning(
                "Guardrail triggered: Attempted to recommend %s for hash role %s on algorithm %s",
                candidate,
                role.value,
                deterministic_algorithm,
            )
            candidate = None
            migration_required = False
            decision = (
                AssessmentDecision.KEEP
                if role in (ContextualRole.CONTENT_ADDRESSING, ContextualRole.DATA_INTEGRITY)
                else AssessmentDecision.REVIEW
            )
            rationale = (
                f"{deterministic_algorithm} functions as a cryptographic hash ({role.value}). "
                "Post-quantum public-key signature algorithms (such as ML-DSA) and key-encapsulation "
                "mechanisms (such as ML-KEM) are not semantic replacements for hash operations. "
                "SHA-256 remains secure against quantum attacks (Grover's algorithm provides 128-bit "
                "collision/preimage resistance)."
            )
            limitations.append(
                "Guardrail correction applied: Incompatible public-key algorithm rejected for hash role."
            )
            tradeoffs.append(
                "Category error prevented: Public-key signatures/KEMs are not replacements for cryptographic hashes."
            )

    # Invariant 2: Key establishment must NEVER be mapped to digital signature algorithms
    elif role == ContextualRole.KEY_ESTABLISHMENT or deterministic_role.upper() == "KEY_ESTABLISHMENT":
        if _matches_family(candidate, SIGNATURE_SCHEMES):
            logger.warning(
                "Guardrail triggered: Attempted to recommend signature %s for key establishment on %s",
                candidate,
                deterministic_algorithm,
            )
            candidate = "ML-KEM-768"
            decision = AssessmentDecision.MIGRATE
            rationale = (
                f"{deterministic_algorithm} is used for key establishment. Digital signature "
                "schemes (ML-DSA) cannot agree keys. The appropriate post-quantum candidate "
                "is ML-KEM (FIPS 203) or a hybrid KEM construction."
            )
            limitations.append(
                "Guardrail correction applied: Corrected invalid signature candidate to ML-KEM for key establishment."
            )

    # Invariant 3: Digital signature must NEVER be mapped to key encapsulation mechanisms
    elif role in (ContextualRole.DIGITAL_SIGNATURE, ContextualRole.SIGNATURE_VERIFICATION) or deterministic_role.upper() == "DIGITAL_SIGNATURE":
        if _matches_family(candidate, KEM_SCHEMES):
            logger.warning(
                "Guardrail triggered: Attempted to recommend KEM %s for signature on %s",
                candidate,
                deterministic_algorithm,
            )
            candidate = "ML-DSA-65"
            decision = AssessmentDecision.MIGRATE
            rationale = (
                f"{deterministic_algorithm} is used for digital signatures. Key-encapsulation "
                "mechanisms (ML-KEM) cannot generate or verify signatures. The appropriate "
                "post-quantum candidate is ML-DSA (FIPS 204) or SLH-DSA (FIPS 205)."
            )
            limitations.append(
                "Guardrail correction applied: Corrected invalid KEM candidate to ML-DSA for digital signature."
            )

    # Invariant 4: Symmetric encryption must NEVER be replaced with public-key algorithms
    elif (
        role == ContextualRole.ENCRYPTION or deterministic_role.upper() == "SYMMETRIC_ENCRYPTION"
    ) and (
        _matches_family(candidate, SIGNATURE_SCHEMES) or _matches_family(candidate, KEM_SCHEMES)
    ):
        logger.warning(
            "Guardrail triggered: Attempted to recommend public-key %s for symmetric cipher %s",
            candidate,
            deterministic_algorithm,
        )
        candidate = None
        migration_required = False
        decision = AssessmentDecision.KEEP
        rationale = (
            f"{deterministic_algorithm} is a symmetric cipher. Symmetric ciphers are not broken "
            "by Shor's algorithm. Review key length and mode rather than replacing the cipher."
        )
        limitations.append(
            "Guardrail correction applied: Public-key algorithm rejected for symmetric cipher."
        )

    # Filter alternatives: if hash or symmetric cipher, remove public key schemes
    if role in HASH_ROLES or deterministic_role.upper() in ("HASH", "SYMMETRIC_ENCRYPTION"):
        filtered_alts = tuple(
            alt
            for alt in assessment.alternatives
            if not (_matches_family(alt, SIGNATURE_SCHEMES) or _matches_family(alt, KEM_SCHEMES))
        )
    else:
        filtered_alts = tuple(assessment.alternatives)

    # If decision is KEEP, candidate should always be None and migration_required False
    if decision == AssessmentDecision.KEEP:
        candidate = None
        migration_required = False

    return replace(
        assessment,
        assessment=decision,
        migration_candidate=candidate,
        pqc_migration_required=migration_required,
        rationale=rationale,
        alternatives=filtered_alts,
        engineering_tradeoffs=tuple(tradeoffs),
        limitations=tuple(limitations),
    )
