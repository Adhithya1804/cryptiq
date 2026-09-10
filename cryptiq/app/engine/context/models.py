"""Typed domain models for the Context-Aware Migration Advisor.

Separates:
- FACT (observed cryptographic construct from deterministic analysis)
- CONTEXT (inferred semantic purpose, domain profile, engineering constraints)
- RECOMMENDATION (advisory decision: KEEP / REVIEW / MIGRATE / INSUFFICIENT_CONTEXT)
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class AssessmentDecision(StrEnum):
    """The high-level advisory recommendation.

    - KEEP: No post-quantum replacement indicated based on available context
      (e.g., hash used for content addressing or cache keys).
    - REVIEW: Context or engineering constraints require human evaluation before migration.
    - MIGRATE: A post-quantum migration path is relevant to this cryptographic role.
    - INSUFFICIENT_CONTEXT: Evidence is inadequate to safely recommend an action.
    """

    KEEP = "KEEP"
    REVIEW = "REVIEW"
    MIGRATE = "MIGRATE"
    INSUFFICIENT_CONTEXT = "INSUFFICIENT_CONTEXT"


class AssessmentConfidence(StrEnum):
    """Confidence in the contextual recommendation."""

    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class ContextualRole(StrEnum):
    """Cryptographic semantic role taxonomy.

    Refines the deterministic inference into a concrete application-level role.
    """

    CONTENT_ADDRESSING = "CONTENT_ADDRESSING"
    DATA_INTEGRITY = "DATA_INTEGRITY"
    HASHING = "HASHING"
    PASSWORD_DERIVATION = "PASSWORD_DERIVATION"
    MAC = "MAC"
    DIGITAL_SIGNATURE = "DIGITAL_SIGNATURE"
    SIGNATURE_VERIFICATION = "SIGNATURE_VERIFICATION"
    KEY_ESTABLISHMENT = "KEY_ESTABLISHMENT"
    KEY_DERIVATION = "KEY_DERIVATION"
    ENCRYPTION = "ENCRYPTION"
    RANDOMNESS = "RANDOMNESS"
    PROTOCOL = "PROTOCOL"
    UNKNOWN = "UNKNOWN"


class ConstraintLevel(StrEnum):
    """Constraint severity levels."""

    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class DomainProfile:
    """Application and engineering constraints surrounding the repository."""

    domain: str = "GENERAL_SOFTWARE"
    latency_sensitivity: ConstraintLevel = ConstraintLevel.UNKNOWN
    bandwidth_constraint: ConstraintLevel = ConstraintLevel.UNKNOWN
    compute_constraint: ConstraintLevel = ConstraintLevel.UNKNOWN
    memory_constraint: ConstraintLevel = ConstraintLevel.UNKNOWN
    battery_constraint: ConstraintLevel = ConstraintLevel.UNKNOWN
    offline_operation: bool | None = None
    signature_frequency: str | None = None
    verification_frequency: str | None = None
    payload_size_sensitivity: ConstraintLevel = ConstraintLevel.UNKNOWN
    data_longevity: str | None = None
    regulatory_requirements: tuple[str, ...] = ()
    platform_constraints: tuple[str, ...] = ()
    interoperability_constraints: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        """Return a clean dictionary representation."""
        return {
            "domain": self.domain,
            "latency_sensitivity": self.latency_sensitivity.value,
            "bandwidth_constraint": self.bandwidth_constraint.value,
            "compute_constraint": self.compute_constraint.value,
            "memory_constraint": self.memory_constraint.value,
            "battery_constraint": self.battery_constraint.value,
            "offline_operation": self.offline_operation,
            "signature_frequency": self.signature_frequency,
            "verification_frequency": self.verification_frequency,
            "payload_size_sensitivity": self.payload_size_sensitivity.value,
            "data_longevity": self.data_longevity,
            "regulatory_requirements": list(self.regulatory_requirements),
            "platform_constraints": list(self.platform_constraints),
            "interoperability_constraints": list(self.interoperability_constraints),
        }

    def profile_hash(self) -> str:
        """Stable hash used as part of cache key."""
        canonical = json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DomainProfile:
        """Construct a DomainProfile safely from dictionary."""
        def _to_level(val: Any) -> ConstraintLevel:
            if isinstance(val, ConstraintLevel):
                return val
            if isinstance(val, str):
                try:
                    return ConstraintLevel(val.upper())
                except ValueError:
                    pass
            return ConstraintLevel.UNKNOWN

        return cls(
            domain=str(data.get("domain", "GENERAL_SOFTWARE")).upper(),
            latency_sensitivity=_to_level(data.get("latency_sensitivity")),
            bandwidth_constraint=_to_level(data.get("bandwidth_constraint")),
            compute_constraint=_to_level(data.get("compute_constraint")),
            memory_constraint=_to_level(data.get("memory_constraint")),
            battery_constraint=_to_level(data.get("battery_constraint")),
            offline_operation=data.get("offline_operation"),
            signature_frequency=data.get("signature_frequency"),
            verification_frequency=data.get("verification_frequency"),
            payload_size_sensitivity=_to_level(data.get("payload_size_sensitivity")),
            data_longevity=data.get("data_longevity"),
            regulatory_requirements=tuple(data.get("regulatory_requirements") or ()),
            platform_constraints=tuple(data.get("platform_constraints") or ()),
            interoperability_constraints=tuple(data.get("interoperability_constraints") or ()),
        )

    @classmethod
    def autonomous_drone(cls) -> DomainProfile:
        """Pre-configured profile for autonomous drone / avionics systems."""
        return cls(
            domain="AUTONOMOUS_DRONE",
            latency_sensitivity=ConstraintLevel.HIGH,
            bandwidth_constraint=ConstraintLevel.HIGH,
            compute_constraint=ConstraintLevel.HIGH,
            memory_constraint=ConstraintLevel.MEDIUM,
            battery_constraint=ConstraintLevel.HIGH,
            offline_operation=True,
            payload_size_sensitivity=ConstraintLevel.HIGH,
            data_longevity="LONG_TERM",
            platform_constraints=("embedded-linux", "arm-cortex-m", "rtos"),
            interoperability_constraints=("mavlink", "custom-firmware-bus"),
        )

    @classmethod
    def cloud_infrastructure(cls) -> DomainProfile:
        """Pre-configured profile for high-throughput cloud services."""
        return cls(
            domain="CLOUD_INFRASTRUCTURE",
            latency_sensitivity=ConstraintLevel.HIGH,
            bandwidth_constraint=ConstraintLevel.LOW,
            compute_constraint=ConstraintLevel.LOW,
            memory_constraint=ConstraintLevel.LOW,
            battery_constraint=ConstraintLevel.LOW,
            offline_operation=False,
            payload_size_sensitivity=ConstraintLevel.LOW,
            data_longevity="VARIABLE",
        )

    @classmethod
    def fintech(cls) -> DomainProfile:
        """Pre-configured profile for banking / financial transaction systems."""
        return cls(
            domain="FINTECH",
            latency_sensitivity=ConstraintLevel.HIGH,
            bandwidth_constraint=ConstraintLevel.LOW,
            compute_constraint=ConstraintLevel.LOW,
            memory_constraint=ConstraintLevel.LOW,
            battery_constraint=ConstraintLevel.LOW,
            offline_operation=False,
            payload_size_sensitivity=ConstraintLevel.LOW,
            data_longevity="LONG_TERM_COMPLIANCE",
            regulatory_requirements=("PCI-DSS", "FIPS-140-3", "SOX"),
        )


@dataclass(frozen=True)
class ExtractedContext:
    """Statically extracted application context around a finding."""

    finding_fingerprint: str
    file_path: str
    enclosing_function: str | None
    enclosing_class: str | None
    module_name: str | None
    surrounding_code: str
    semantic_clues: tuple[str, ...] = ()
    inferred_role_candidate: ContextualRole = ContextualRole.UNKNOWN
    context_summary: str = ""


@dataclass(frozen=True)
class ContextualAssessment:
    """The complete contextual assessment output.

    Visibly structures:
    - FACT (what was observed)
    - CONTEXT (how it functions in application & domain context)
    - RECOMMENDATION (advisory decision and engineering rationale)
    """

    finding_id: str | None
    fingerprint: str
    assessment: AssessmentDecision
    confidence: AssessmentConfidence
    contextual_role: ContextualRole
    rationale: str
    pqc_migration_required: bool
    migration_candidate: str | None
    alternatives: tuple[str, ...] = ()
    engineering_tradeoffs: tuple[str, ...] = ()
    required_context: tuple[str, ...] = ()
    evidence_interpretation: str = ""
    knowledge_sources: tuple[dict[str, Any], ...] = ()
    limitations: tuple[str, ...] = ()
    domain_profile: DomainProfile = field(default_factory=DomainProfile)
    generated_by: str = "heuristic_advisor"
    model: str | None = None
    prompt_version: str | None = None
    cached: bool = False

    def to_dict(self) -> dict[str, Any]:
        """Render to dictionary suitable for API and CLI."""
        return {
            "finding_id": self.finding_id,
            "fingerprint": self.fingerprint,
            "assessment": self.assessment.value,
            "confidence": self.confidence.value,
            "contextual_role": self.contextual_role.value,
            "rationale": self.rationale,
            "pqc_migration_required": self.pqc_migration_required,
            "migration_candidate": self.migration_candidate,
            "alternatives": list(self.alternatives),
            "engineering_tradeoffs": list(self.engineering_tradeoffs),
            "required_context": list(self.required_context),
            "evidence_interpretation": self.evidence_interpretation,
            "knowledge_sources": list(self.knowledge_sources),
            "limitations": list(self.limitations),
            "domain_profile": self.domain_profile.to_dict(),
            "generated_by": self.generated_by,
            "model": self.model,
            "prompt_version": self.prompt_version,
            "cached": self.cached,
        }
