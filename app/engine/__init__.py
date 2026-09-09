"""
Cryptiq Static Analysis Engine.
Implements Phases 5-8 of the Master Specification:
- Phase 5: Base Rule Protocol, RSA Detection, Evidence Extraction
- Phase 6: Expanded Rules (ECDSA, Ed25519, ECDH, X25519, AES, Hashes) & RuleRegistry
- Phase 7: Role Engine (CryptoRole taxonomy, Confidence, RoleClassifier)
- Phase 8: PQC Migration Mapping Engine (MigrationPath, PQCMapper, map_review_path)
"""
from app.engine.evidence import EvidenceExtractor
from app.engine.models import (
    AnalysisContext,
    AnalysisResult,
    Confidence,
    CryptoRole,
    Evidence,
    FindingResult,
    MigrationPath,
    ParsedFile,
    RawObservation,
    RoleInference,
    RuleMatch,
)
from app.engine.pqc import (
    DEFAULT_PQC_RULESET_VERSION,
    PQCMapper,
    get_pqc_mapping,
    map_review_path,
)
from app.engine.roles import RoleClassifier
from app.engine.rules import (
    AESRule,
    CryptoRule,
    ECDHRule,
    ECDSARule,
    Ed25519Rule,
    HashRule,
    RSARule,
    RuleRegistry,
    X25519Rule,
)

__all__ = [
    # Models
    "CryptoRole",
    "Confidence",
    "RoleInference",
    "MigrationPath",
    "RawObservation",
    "RuleMatch",
    "Evidence",
    "ParsedFile",
    "AnalysisContext",
    "FindingResult",
    "AnalysisResult",
    # Evidence
    "EvidenceExtractor",
    # Roles
    "RoleClassifier",
    # PQC
    "PQCMapper",
    "map_review_path",
    "get_pqc_mapping",
    "DEFAULT_PQC_RULESET_VERSION",
    # Rules
    "CryptoRule",
    "RuleRegistry",
    "RSARule",
    "ECDSARule",
    "Ed25519Rule",
    "ECDHRule",
    "X25519Rule",
    "AESRule",
    "HashRule",
]
