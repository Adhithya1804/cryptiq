"""Deterministic Migration Review Priority Scorer for Cryptiq.

Strictly scores MIGRATION_REVIEW_PRIORITY (not vulnerability severity).
"""

from __future__ import annotations

from typing import Any, List, Optional

from cryptiq.core.enums import ConfidenceLevel, CryptoRole, PriorityLevel
from cryptiq.core.models import ImpactResult, PriorityResult
from cryptiq.priority.rules import (
    ASYMMETRIC_ALGORITHMS,
    HASH_ALGORITHMS,
    LEGACY_HASH_ALGORITHMS,
    PQC_NATIVE_ALGORITHMS,
    SYMMETRIC_ALGORITHMS,
)


def _extract(obj: Any, key: str, default: Any = None) -> Any:
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


class PriorityScorer:
    """Calculates deterministic Migration Review Priority based on cryptographic evidence."""

    def score(
        self,
        finding: Any,
        role: Optional[Any] = None,
        impact: Optional[Any] = None,
    ) -> PriorityResult:
        """Deterministically score migration priority without LLM or probabilistic guesswork."""
        # 1. Extract algorithm
        raw_algo = _extract(finding, "algorithm", "") or ""
        algo_normalized = str(raw_algo).strip().upper()

        # 2. Extract role (explicit argument takes precedence over finding attribute)
        raw_role = role or _extract(finding, "role", None)
        if isinstance(raw_role, CryptoRole):
            crypto_role = raw_role
        elif isinstance(raw_role, str):
            try:
                crypto_role = CryptoRole(raw_role)
            except ValueError:
                crypto_role = CryptoRole.UNKNOWN
        else:
            crypto_role = CryptoRole.UNKNOWN

        # 3. Extract confidence
        raw_conf = _extract(finding, "confidence", ConfidenceLevel.CONFIRMED)
        if isinstance(raw_conf, ConfidenceLevel):
            confidence = raw_conf
        elif isinstance(raw_conf, str):
            try:
                confidence = ConfidenceLevel(raw_conf.upper())
            except ValueError:
                confidence = ConfidenceLevel.UNKNOWN
        else:
            confidence = ConfidenceLevel.UNKNOWN

        reasons: List[str] = []
        numeric_score = 0

        # Check for unknown / unconfirmed state first
        if crypto_role == CryptoRole.UNKNOWN or confidence == ConfidenceLevel.UNKNOWN or algo_normalized in {"", "UNKNOWN"}:
            reasons.append("Unconfirmed or unknown cryptographic primitive")
            reasons.append("Low-confidence evidence requiring manual triage")
            return PriorityResult(
                level=PriorityLevel.LOW,
                reasons=reasons,
                score=10,
            )

        # Check for already quantum-resistant primitives
        if algo_normalized in PQC_NATIVE_ALGORITHMS or "ML-KEM" in algo_normalized or "ML-DSA" in algo_normalized:
            reasons.append("Direct post-quantum cryptographic primitive observed")
            reasons.append("Not a legacy migration candidate; validate implementation standards")
            return PriorityResult(
                level=PriorityLevel.LOW,
                reasons=reasons,
                score=20,
            )

        # Determine if algorithm is asymmetric / public-key
        is_asymmetric = (
            algo_normalized in ASYMMETRIC_ALGORITHMS
            or "RSA" in algo_normalized
            or "ECDSA" in algo_normalized
            or "ED25519" in algo_normalized
            or "X25519" in algo_normalized
            or "DIFFIE" in algo_normalized
            or "DH" in algo_normalized
        )

        # Confidence weight
        if confidence == ConfidenceLevel.CONFIRMED:
            reasons.append("High-confidence evidence")
            numeric_score += 30
        elif confidence == ConfidenceLevel.INFERRED:
            reasons.append("Inferred source evidence")
            numeric_score += 15

        # Role and Algorithm interactions
        if is_asymmetric:
            reasons.append("Public-key cryptography")
            numeric_score += 40

            if crypto_role == CryptoRole.DIGITAL_SIGNATURE:
                reasons.append("Digital signature operation")
                reasons.append("Security-relevant operation")
                reasons.append("Requires signature migration review (FIPS 204 ML-DSA / FIPS 205 SLH-DSA)")
                numeric_score += 30
            elif crypto_role == CryptoRole.KEY_ESTABLISHMENT:
                reasons.append("Key establishment operation")
                reasons.append("Security-relevant operation")
                reasons.append("Requires key encapsulation migration review (FIPS 203 ML-KEM / hybrid)")
                numeric_score += 30
            elif crypto_role == CryptoRole.ENCRYPTION:
                reasons.append("Asymmetric encryption operation")
                reasons.append("Security-relevant operation")
                numeric_score += 25
            elif crypto_role == CryptoRole.TLS_CERTIFICATE:
                reasons.append("Public-key TLS/certificate usage")
                reasons.append("Security-relevant operation")
                numeric_score += 25
            else:
                reasons.append("Asymmetric primitive with unspecified role")
                numeric_score += 10

        elif algo_normalized in HASH_ALGORITHMS or crypto_role == CryptoRole.HASH:
            reasons.append("Hash function primitive; not directly quantum-vulnerable")
            numeric_score += 15
            if algo_normalized in LEGACY_HASH_ALGORITHMS or "SHA1" in algo_normalized or "MD5" in algo_normalized:
                reasons.append(f"Legacy hash {algo_normalized} subject to classical collision review")
                numeric_score += 25
            else:
                reasons.append("Separate hash integrity review; do not map directly to PQC KEM or signature")

        elif algo_normalized in SYMMETRIC_ALGORITHMS or crypto_role == CryptoRole.SYMMETRIC_ENCRYPTION:
            reasons.append("Symmetric cryptography primitive")
            reasons.append("Separate symmetric security review; not broken by polynomial-time quantum algorithms")
            numeric_score += 15

        else:
            reasons.append(f"Observed cryptographic primitive: {algo_normalized}")
            numeric_score += 10

        # Evaluate Impact breadth if provided
        if impact is not None:
            nodes = _extract(impact, "nodes", []) or []
            if len(nodes) >= 4:
                reasons.append("Wider static blast radius identified across class or caller hierarchy")
                numeric_score += 10

        # Final level assignment strictly by deterministic threshold
        if numeric_score >= 80:
            level = PriorityLevel.HIGH
        elif numeric_score >= 40:
            level = PriorityLevel.MEDIUM
        else:
            level = PriorityLevel.LOW

        return PriorityResult(
            level=level,
            reasons=reasons,
            score=numeric_score,
        )
