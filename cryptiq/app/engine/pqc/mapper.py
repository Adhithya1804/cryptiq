"""Mapping a cryptographic role to its post-quantum review path.

A review path is **not** a replacement. Cryptiq never says "swap RSA for
ML-DSA": choosing a scheme, a parameter set and a migration order is work a
cryptographer does with the whole system in front of them. What this stage
says is narrower and checkable — which body of guidance a reviewer should open
for this finding, and why.

The mapping is a fixed table keyed on the role and the algorithm family. A
combination the table does not cover falls through to manual review rather
than being approximated.
"""

from dataclasses import dataclass
from enum import StrEnum

from app.engine.roles import CryptographicRole


class PqcReviewPath(StrEnum):
    """The body of guidance a finding should be reviewed against."""

    SIGNATURE_MIGRATION = "ML-DSA / SLH-DSA"
    KEY_ENCAPSULATION_MIGRATION = "ML-KEM"
    SYMMETRIC_REVIEW = "KEY / IMPLEMENTATION REVIEW"
    HASH_POLICY_REVIEW = "HASH / POLICY REVIEW"
    MANUAL_REVIEW = "MANUAL REVIEW"


# Public-key algorithms a quantum computer breaks outright. Only these are
# migration candidates; everything else is a review of some other kind.
SIGNATURE_ALGORITHMS = frozenset({"RSA", "ECDSA", "ED25519", "ED448", "DSA"})
KEY_ESTABLISHMENT_ALGORITHMS = frozenset(
    {"RSA", "ECDH", "X25519", "X448", "DH", "DIFFIE-HELLMAN"}
)
SYMMETRIC_ALGORITHMS = frozenset({"AES", "CHACHA20", "3DES", "DES", "CAMELLIA"})


@dataclass(frozen=True)
class PqcAssessment:
    """A review path, why it applies, and whether a migration is implied.

    ``is_migration_candidate`` is true only for the two public-key paths. A
    symmetric or hash finding is inventory to review, not something to
    migrate, and conflating the two would inflate the migration backlog.
    """

    review_path: PqcReviewPath
    rationale: str
    is_migration_candidate: bool


def map_review_path(algorithm: str, role: CryptographicRole) -> PqcAssessment:
    """Return the review path for an algorithm used in a given role."""
    name = algorithm.strip().upper()

    if role is CryptographicRole.DIGITAL_SIGNATURE and name in SIGNATURE_ALGORITHMS:
        return PqcAssessment(
            review_path=PqcReviewPath.SIGNATURE_MIGRATION,
            rationale=(
                f"{algorithm} signatures are broken by Shor's algorithm. Review against "
                "the FIPS 204 (ML-DSA) and FIPS 205 (SLH-DSA) signature standards."
            ),
            is_migration_candidate=True,
        )

    if role is CryptographicRole.KEY_ESTABLISHMENT and name in KEY_ESTABLISHMENT_ALGORITHMS:
        return PqcAssessment(
            review_path=PqcReviewPath.KEY_ENCAPSULATION_MIGRATION,
            rationale=(
                f"{algorithm} key establishment is broken by Shor's algorithm, and traffic "
                "captured today can be decrypted later. Review against the FIPS 203 "
                "(ML-KEM) standard, including hybrid options."
            ),
            is_migration_candidate=True,
        )

    if role is CryptographicRole.SYMMETRIC_ENCRYPTION and name in SYMMETRIC_ALGORITHMS:
        return PqcAssessment(
            review_path=PqcReviewPath.SYMMETRIC_REVIEW,
            rationale=(
                f"{algorithm} is not broken by Shor's algorithm. Review the key length, "
                "the mode and the implementation rather than replacing the cipher."
            ),
            is_migration_candidate=False,
        )

    if role is CryptographicRole.HASH:
        return PqcAssessment(
            review_path=PqcReviewPath.HASH_POLICY_REVIEW,
            rationale=(
                f"{algorithm} is a hash, not a public-key primitive. Review it against "
                "hash policy on its own terms; it does not map to a KEM or a signature."
            ),
            is_migration_candidate=False,
        )

    return PqcAssessment(
        review_path=PqcReviewPath.MANUAL_REVIEW,
        rationale=(
            f"{algorithm} in the role {role.value} is not covered by the mapping table. "
            "A reviewer must establish the review path."
        ),
        is_migration_candidate=False,
    )
