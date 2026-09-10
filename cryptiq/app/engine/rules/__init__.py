"""Rules: match cryptographic constructs in an AST and emit raw observations.

A rule reports only what the syntax establishes. Roles, post-quantum review
paths and priority are decided by later stages from these observations.
"""

from app.engine.rules.aes import AesRule
from app.engine.rules.base import (
    AnalysisContext,
    CryptoOperation,
    CryptoRule,
    EvidenceBasis,
    MatchConfidence,
    RuleMatch,
)
from app.engine.rules.ecdh import EcdhRule
from app.engine.rules.ecdsa import EcdsaRule
from app.engine.rules.ed25519 import Ed25519Rule
from app.engine.rules.hashes import HashRule
from app.engine.rules.registry import (
    all_rules,
    get_rule,
    register,
    registered_rule_ids,
)
from app.engine.rules.rsa import RSA_MODULE, RsaRule
from app.engine.rules.rsa import RULE_ID as RSA_RULE_ID
from app.engine.rules.runner import evaluate_file, evaluate_files
from app.engine.rules.x25519 import X25519Rule

__all__ = [
    "RSA_MODULE",
    "RSA_RULE_ID",
    "AesRule",
    "AnalysisContext",
    "CryptoOperation",
    "CryptoRule",
    "EcdhRule",
    "EcdsaRule",
    "Ed25519Rule",
    "EvidenceBasis",
    "HashRule",
    "MatchConfidence",
    "RsaRule",
    "RuleMatch",
    "X25519Rule",
    "all_rules",
    "evaluate_file",
    "evaluate_files",
    "get_rule",
    "register",
    "registered_rule_ids",
]
