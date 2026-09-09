from __future__ import annotations

from app.engine.models import CryptoRole, MigrationPath
from app.engine.pqc.registry import (
    DEFAULT_PQC_RULESET_VERSION,
    get_pqc_mapping,
)


class PQCMapper:
    """
    Deterministic Post-Quantum Cryptography (PQC) review path mapper.
    Maps algorithm and established cryptographic role to NIST post-quantum migration review recommendations.
    Strictly depends on CryptoRole; never maps on algorithm alone.
    """

    def __init__(self, pqc_ruleset_version: str = DEFAULT_PQC_RULESET_VERSION) -> None:
        self.pqc_ruleset_version = pqc_ruleset_version

    def map(
        self,
        algorithm: str,
        role: CryptoRole | str,
    ) -> MigrationPath:
        """
        Pure and deterministic mapping of (algorithm, role) to recommended MigrationPath.
        Fails safely to 'Manual review' for unknown or invalid combinations.
        """
        # Normalize role input if provided as string or enum
        norm_role: CryptoRole
        if isinstance(role, CryptoRole):
            norm_role = role
        elif isinstance(role, str):
            try:
                norm_role = CryptoRole(role)
            except ValueError:
                norm_role = CryptoRole.UNKNOWN
        else:
            norm_role = CryptoRole.UNKNOWN

        return get_pqc_mapping(
            algorithm=algorithm,
            role=norm_role,
            ruleset_version=self.pqc_ruleset_version,
        )


def map_review_path(
    algorithm: str,
    role: CryptoRole | str,
    pqc_ruleset_version: str = DEFAULT_PQC_RULESET_VERSION,
) -> MigrationPath:
    """
    Convenience function matching the spec Section 45 signature.
    """
    mapper = PQCMapper(pqc_ruleset_version=pqc_ruleset_version)
    return mapper.map(algorithm, role)
