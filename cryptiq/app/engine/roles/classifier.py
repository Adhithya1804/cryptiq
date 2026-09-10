"""Classifying what a detected construct is for.

The role is an **inference**, not an observation. The rules established that
``RSAPrivateKey.sign`` was called at a source location; this stage says that
such a call is a digital signature. The distinction matters downstream: a
reviewer can check an observation against the file, but a role is a statement
this engine is making on their behalf, so it carries its own rationale.

Classification is a fixed table keyed on the algorithm and the operation. No
model, no heuristic, no scoring.
"""

from dataclasses import dataclass
from enum import StrEnum

from app.engine.rules import CryptoOperation, RuleMatch


class CryptographicRole(StrEnum):
    """What a construct does cryptographically.

    Mirrors ``app.db.models.enums.CryptographicRole`` by value. PROTOCOL is
    part of the vocabulary but nothing produces it yet: it is for a rule that
    recognises a protocol implementation such as TLS, which does not exist.
    """

    DIGITAL_SIGNATURE = "DIGITAL_SIGNATURE"
    KEY_ESTABLISHMENT = "KEY_ESTABLISHMENT"
    SYMMETRIC_ENCRYPTION = "SYMMETRIC_ENCRYPTION"
    HASH = "HASH"
    PROTOCOL = "PROTOCOL"
    UNKNOWN = "UNKNOWN"


# Algorithms whose whole purpose is signing. Generating one of these keys can
# only be preparation for a signature.
SIGNATURE_ALGORITHMS = frozenset({"ECDSA", "ED25519", "ED448"})

# Algorithms whose whole purpose is agreeing a shared secret.
KEY_AGREEMENT_ALGORITHMS = frozenset({"ECDH", "X25519", "X448", "DH", "DIFFIE-HELLMAN"})

# Algorithms usable for both signing and key transport. Generating one of
# these says nothing about which.
DUAL_USE_ALGORITHMS = frozenset({"RSA"})

SYMMETRIC_ALGORITHMS = frozenset({"AES", "CHACHA20", "3DES", "DES", "CAMELLIA"})

SIGNING_OPERATIONS = frozenset({CryptoOperation.SIGN, CryptoOperation.VERIFY})

# RSA encryption is key transport: a symmetric key is wrapped under a public
# key, which is the problem ML-KEM replaces.
KEY_TRANSPORT_OPERATIONS = frozenset({CryptoOperation.ENCRYPT, CryptoOperation.DECRYPT})


@dataclass(frozen=True)
class RoleAssessment:
    """A role and the fixed sentence explaining why it was chosen."""

    role: CryptographicRole
    rationale: str


def classify(match: RuleMatch) -> RoleAssessment:
    """Return the cryptographic role of one observation."""
    algorithm = match.algorithm.strip().upper()
    operation = match.operation

    if match.primitive.strip().upper() == "HASH":
        return RoleAssessment(
            CryptographicRole.HASH,
            f"{match.algorithm} is a hash function.",
        )

    if algorithm in SYMMETRIC_ALGORITHMS:
        return RoleAssessment(
            CryptographicRole.SYMMETRIC_ENCRYPTION,
            f"{match.algorithm} is a symmetric cipher.",
        )

    if operation in SIGNING_OPERATIONS:
        return RoleAssessment(
            CryptographicRole.DIGITAL_SIGNATURE,
            f"{match.api} performs a {operation.value.lower()} operation.",
        )

    if operation is CryptoOperation.KEY_ESTABLISHMENT:
        return RoleAssessment(
            CryptographicRole.KEY_ESTABLISHMENT,
            f"{match.api} agrees a shared secret.",
        )

    if operation in KEY_TRANSPORT_OPERATIONS and algorithm in DUAL_USE_ALGORITHMS:
        return RoleAssessment(
            CryptographicRole.KEY_ESTABLISHMENT,
            f"{match.algorithm} encryption transports a key under a public key.",
        )

    if operation is CryptoOperation.KEY_GENERATION:
        return _classify_key_generation(match, algorithm)

    return RoleAssessment(
        CryptographicRole.UNKNOWN,
        f"{match.api} does not establish what the key is used for.",
    )


def _classify_key_generation(match: RuleMatch, algorithm: str) -> RoleAssessment:
    """Return the role of a key generation, which depends on the algorithm.

    A single-purpose algorithm settles it: an Ed25519 key can only sign and an
    X25519 key can only agree. A dual-use algorithm such as RSA does not, so
    generating one is left UNKNOWN rather than guessed at.
    """
    if algorithm in SIGNATURE_ALGORITHMS:
        return RoleAssessment(
            CryptographicRole.DIGITAL_SIGNATURE,
            f"{match.algorithm} keys can only be used for signatures.",
        )

    if algorithm in KEY_AGREEMENT_ALGORITHMS:
        return RoleAssessment(
            CryptographicRole.KEY_ESTABLISHMENT,
            f"{match.algorithm} keys can only be used for key agreement.",
        )

    if algorithm in DUAL_USE_ALGORITHMS:
        return RoleAssessment(
            CryptographicRole.UNKNOWN,
            (
                f"{match.algorithm} keys sign and transport keys, so generating one "
                "does not establish the role."
            ),
        )

    return RoleAssessment(
        CryptographicRole.UNKNOWN,
        f"{match.algorithm} key generation has no established role.",
    )
