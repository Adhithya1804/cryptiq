"""Migration review priority.

This is a review ordering, not a vulnerability severity: it answers "which
cryptographic call should a human look at first when planning a post-quantum
migration". Scoring is a fixed table of additions with fixed thresholds, so
the same observation always lands in the same band.
"""

from dataclasses import dataclass
from enum import StrEnum

from app.engine.impact.models import ImpactResult
from app.engine.priority.rules import (
    ASYMMETRIC_ALGORITHMS,
    HASH_ALGORITHMS,
    LEGACY_HASH_ALGORITHMS,
    PQC_ALGORITHMS,
    SYMMETRIC_ALGORITHMS,
)
from app.engine.roles import CryptographicRole
from app.engine.rules import CryptoOperation, MatchConfidence, RuleMatch


class ReviewPriority(StrEnum):
    """Migration review bands.

    Mirrors ``app.db.models.enums.ReviewPriority`` by value. CRITICAL and
    INFORMATIONAL exist in the persisted vocabulary but are not produced by
    this engine, which has no evidence that would justify them.
    """

    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    INFORMATIONAL = "INFORMATIONAL"


# Score contributions, all fixed.
CONFIDENCE_POINTS = {
    MatchConfidence.HIGH: 30,
    MatchConfidence.MEDIUM: 15,
    MatchConfidence.LOW: 5,
    MatchConfidence.UNKNOWN: 0,
}

ASYMMETRIC_POINTS = 40
LEGACY_HASH_POINTS = 25
HASH_POINTS = 15
SYMMETRIC_POINTS = 15
UNCLASSIFIED_POINTS = 10
BROAD_IMPACT_POINTS = 10

# Roles whose risk outlives the operation: a signature made today can be
# forged later, and traffic protected by a key agreed today can be captured
# now and read later. A finding in one of these roles scores as a key
# operation even when its own operation would score lower -- RSA key
# transport is spelled ``encrypt`` but is key establishment.
LONG_LIVED_ROLES = frozenset(
    {CryptographicRole.DIGITAL_SIGNATURE, CryptographicRole.KEY_ESTABLISHMENT}
)

KEY_OPERATION_POINTS = 30

# Operations that carry long-lived risk: a signature or a key agreement made
# today can be attacked later, so they lead the review queue.
OPERATION_POINTS = {
    CryptoOperation.SIGN: 30,
    CryptoOperation.VERIFY: 30,
    CryptoOperation.KEY_GENERATION: 30,
    CryptoOperation.KEY_ESTABLISHMENT: 30,
    CryptoOperation.ENCRYPT: 25,
    CryptoOperation.DECRYPT: 25,
    # Naming a primitive is inventory, not an operation on data, and a hash is
    # reviewed on its own terms rather than migrated.
    CryptoOperation.CONSTRUCTION: 10,
    CryptoOperation.HASH: 10,
}

# A graph reaching a class or a module, not just a function, is broader.
BROAD_IMPACT_NODES = 5

HIGH_THRESHOLD = 80
MEDIUM_THRESHOLD = 40


@dataclass(frozen=True)
class PriorityResult:
    """A priority band, the score behind it, and why."""

    level: ReviewPriority
    score: int
    reasons: tuple[str, ...]


def score(
    match: RuleMatch,
    impact: ImpactResult | None = None,
    role: CryptographicRole | None = None,
) -> PriorityResult:
    """Return the migration review priority of one observation.

    The role is an additional input, never the whole answer: it raises an
    operation whose spelling understates its risk, and it is recorded in the
    reasons. The algorithm family, the confidence and the blast radius still
    carry the rest of the score.
    """
    algorithm = match.algorithm.strip().upper()
    reasons: list[str] = []
    points = 0

    if _is_post_quantum(algorithm):
        return PriorityResult(
            level=ReviewPriority.LOW,
            score=CONFIDENCE_POINTS[match.confidence],
            reasons=(
                f"{algorithm} is already a post-quantum primitive.",
                "Not a migration candidate; review the implementation, not the algorithm.",
            ),
        )

    points += CONFIDENCE_POINTS[match.confidence]
    reasons.append(f"{match.confidence.value} confidence from {match.evidence_basis.value}.")

    points += _algorithm_points(algorithm, reasons)

    operation_points = OPERATION_POINTS.get(match.operation, 0)
    if role in LONG_LIVED_ROLES and operation_points < KEY_OPERATION_POINTS:
        operation_points = KEY_OPERATION_POINTS
        reasons.append(f"{match.operation.value} operation in the role {role.value}.")
    elif operation_points:
        reasons.append(f"{match.operation.value} operation.")
    if operation_points:
        points += operation_points

    if role is not None and role is not CryptographicRole.UNKNOWN:
        reasons.append(f"Classified as {role.value}.")

    if impact is not None and impact.node_count >= BROAD_IMPACT_NODES:
        points += BROAD_IMPACT_POINTS
        reasons.append(
            f"Blast radius spans {impact.node_count} static elements."
        )

    return PriorityResult(level=_band(points), score=points, reasons=tuple(reasons))


def _is_post_quantum(algorithm: str) -> bool:
    return algorithm in PQC_ALGORITHMS


def _algorithm_points(algorithm: str, reasons: list[str]) -> int:
    """Score the algorithm family and record why."""
    if algorithm in ASYMMETRIC_ALGORITHMS:
        reasons.append(f"{algorithm} is public-key cryptography broken by Shor's algorithm.")
        return ASYMMETRIC_POINTS

    if algorithm in LEGACY_HASH_ALGORITHMS:
        reasons.append(f"{algorithm} is a legacy hash with known classical weaknesses.")
        return LEGACY_HASH_POINTS

    if algorithm in HASH_ALGORITHMS:
        reasons.append(f"{algorithm} is a hash; review its length, not its family.")
        return HASH_POINTS

    if algorithm in SYMMETRIC_ALGORITHMS:
        reasons.append(f"{algorithm} is symmetric; a key-length review, not a migration.")
        return SYMMETRIC_POINTS

    reasons.append(f"{algorithm} is not in the classified algorithm tables.")
    return UNCLASSIFIED_POINTS


def _band(points: int) -> ReviewPriority:
    if points >= HIGH_THRESHOLD:
        return ReviewPriority.HIGH
    if points >= MEDIUM_THRESHOLD:
        return ReviewPriority.MEDIUM
    return ReviewPriority.LOW
