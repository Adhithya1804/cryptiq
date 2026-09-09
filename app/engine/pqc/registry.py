from __future__ import annotations

from typing import Any

from app.engine.models import CryptoRole, MigrationPath

DEFAULT_PQC_RULESET_VERSION = "0.1.0"

# Static deterministic ruleset v0.1.0 adhering to NIST Post-Quantum Cryptography standards
# (FIPS 203 ML-KEM, FIPS 204 ML-DSA, FIPS 205 SLH-DSA)
PQC_MAPPING_RULESET_V0_1_0: dict[tuple[str, CryptoRole], tuple[list[str], str]] = {
    # Public-key signatures -> ML-DSA / SLH-DSA
    ("RSA", CryptoRole.DIGITAL_SIGNATURE): (
        ["ML-DSA", "SLH-DSA"],
        "Transition RSA signatures to NIST FIPS 204 (ML-DSA) or FIPS 205 (SLH-DSA).",
    ),
    ("ECDSA", CryptoRole.DIGITAL_SIGNATURE): (
        ["ML-DSA", "SLH-DSA"],
        "Transition ECDSA signatures to NIST FIPS 204 (ML-DSA) or FIPS 205 (SLH-DSA).",
    ),
    ("ED25519", CryptoRole.DIGITAL_SIGNATURE): (
        ["ML-DSA", "SLH-DSA"],
        "Transition Ed25519 signatures to NIST FIPS 204 (ML-DSA) or FIPS 205 (SLH-DSA).",
    ),

    # Key establishment / key exchange -> ML-KEM
    ("RSA", CryptoRole.KEY_ESTABLISHMENT): (
        ["ML-KEM"],
        "Transition RSA key encapsulation/transport to NIST FIPS 203 (ML-KEM).",
    ),
    ("ECDH", CryptoRole.KEY_ESTABLISHMENT): (
        ["ML-KEM"],
        "Transition ECDH key exchange to NIST FIPS 203 (ML-KEM).",
    ),
    ("X25519", CryptoRole.KEY_ESTABLISHMENT): (
        ["ML-KEM"],
        "Transition X25519 key exchange to NIST FIPS 203 (ML-KEM).",
    ),
}

# Role-based fallback rules for symmetric ciphers and hashing
ROLE_BASED_DEFAULTS_V0_1_0: dict[CryptoRole, tuple[list[str], str]] = {
    CryptoRole.SYMMETRIC_ENCRYPTION: (
        ["Key/implementation review"],
        "Review symmetric key length (prefer AES-256 for Grover resistance) and authenticated modes.",
    ),
    CryptoRole.HASH: (
        ["Hash/policy review"],
        "Review hash output length and collision resistance against quantum policy requirements.",
    ),
    CryptoRole.UNKNOWN: (
        ["Manual review"],
        "Ambiguous or unknown cryptographic usage requires manual review.",
    ),
    CryptoRole.PROTOCOL: (
        ["Manual review"],
        "Protocol-level cryptographic usage requires architecture review.",
    ),
}

PQC_RULESETS: dict[str, dict[str, Any]] = {
    "0.1.0": {
        "explicit": PQC_MAPPING_RULESET_V0_1_0,
        "role_defaults": ROLE_BASED_DEFAULTS_V0_1_0,
    },
}


def get_pqc_mapping(
    algorithm: str,
    role: CryptoRole,
    ruleset_version: str = DEFAULT_PQC_RULESET_VERSION,
) -> MigrationPath:
    """
    Retrieve the deterministic MigrationPath for an algorithm and role under a specific ruleset version.
    Fails securely to 'Manual review' if ruleset version or combination is unknown.
    """
    ruleset = PQC_RULESETS.get(ruleset_version)
    if not ruleset:
        return MigrationPath(
            review_path=["Manual review"],
            pqc_ruleset_version=ruleset_version,
            notes=f"Unknown PQC ruleset version '{ruleset_version}'; defaulting to manual review.",
        )

    algo_clean = (algorithm or "").strip().upper()

    # 1. Check exact (algorithm, role) mapping
    explicit_map = ruleset["explicit"]
    if (algo_clean, role) in explicit_map:
        review_path, notes = explicit_map[(algo_clean, role)]
        return MigrationPath(
            review_path=list(review_path),
            pqc_ruleset_version=ruleset_version,
            notes=notes,
        )

    # 2. Check role-based defaults (e.g. AES -> SYMMETRIC_ENCRYPTION, SHA -> HASH)
    role_defaults = ruleset["role_defaults"]
    if role in role_defaults:
        review_path, notes = role_defaults[role]
        return MigrationPath(
            review_path=list(review_path),
            pqc_ruleset_version=ruleset_version,
            notes=notes,
        )

    # 3. Secure fallback for unhandled / invalid combinations
    return MigrationPath(
        review_path=["Manual review"],
        pqc_ruleset_version=ruleset_version,
        notes="Unrecognized algorithm/role combination; defaulting to manual review.",
    )
