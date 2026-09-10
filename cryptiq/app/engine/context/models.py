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


_MAX_TAG_CHARS = 120
_MAX_TAGS = 20
_MAX_DOMAIN_CHARS = 64
_LIST_FIELDS = (
    "regulatory_requirements",
    "platform_constraints",
    "interoperability_constraints",
)
_TEXT_FIELDS = (
    "latency_sensitivity",
    "bandwidth_constraint",
    "compute_constraint",
    "memory_constraint",
    "battery_constraint",
    "payload_size_sensitivity",
    "signature_frequency",
    "verification_frequency",
    "data_longevity",
)


def _clamp_profile_data(data: dict[str, Any]) -> dict[str, Any]:
    """Return a shallow copy of ``data`` with every free-text field length-bounded."""
    out = dict(data)
    if "domain" in out and out["domain"] is not None:
        out["domain"] = str(out["domain"])[:_MAX_DOMAIN_CHARS]
    for field_name in _TEXT_FIELDS:
        value = out.get(field_name)
        if isinstance(value, str):
            out[field_name] = value[:_MAX_TAG_CHARS]
    for field_name in _LIST_FIELDS:
        value = out.get(field_name)
        if isinstance(value, (list, tuple)):
            out[field_name] = [
                str(item)[:_MAX_TAG_CHARS] for item in list(value)[:_MAX_TAGS]
            ]
    return out


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
        """Construct a DomainProfile safely from dictionary, inheriting preset defaults.

        Free-text fields are clamped here as well as at the API schema, so a
        caller that reaches this without Pydantic validation (the CLI, an
        internal call) still cannot produce an unbounded profile -- it is
        forwarded into the migration-assessment prompt and forms a cache key.
        """
        data = _clamp_profile_data(data)
        domain_name = str(data.get("domain", "GENERAL_SOFTWARE")).upper().replace("-", "_")
        base: DomainProfile | None = None
        if domain_name == "AUTONOMOUS_DRONE":
            base = cls.autonomous_drone()
        elif domain_name == "CLOUD_INFRASTRUCTURE":
            base = cls.cloud_infrastructure()
        elif domain_name == "FINTECH":
            base = cls.fintech()

        def _to_level(val: Any, default: ConstraintLevel) -> ConstraintLevel:
            if isinstance(val, ConstraintLevel):
                if val != ConstraintLevel.UNKNOWN or default == ConstraintLevel.UNKNOWN:
                    return val
                return default
            if isinstance(val, str) and val.strip():
                try:
                    lvl = ConstraintLevel(val.upper())
                    if lvl != ConstraintLevel.UNKNOWN or default == ConstraintLevel.UNKNOWN:
                        return lvl
                except ValueError:
                    pass
            return default

        base_latency = base.latency_sensitivity if base else ConstraintLevel.UNKNOWN
        base_bw = base.bandwidth_constraint if base else ConstraintLevel.UNKNOWN
        base_compute = base.compute_constraint if base else ConstraintLevel.UNKNOWN
        base_mem = base.memory_constraint if base else ConstraintLevel.UNKNOWN
        base_battery = base.battery_constraint if base else ConstraintLevel.UNKNOWN
        base_payload = base.payload_size_sensitivity if base else ConstraintLevel.UNKNOWN

        return cls(
            domain=domain_name,
            latency_sensitivity=_to_level(data.get("latency_sensitivity"), base_latency)
            if data.get("latency_sensitivity") is not None
            else base_latency,
            bandwidth_constraint=_to_level(data.get("bandwidth_constraint"), base_bw)
            if data.get("bandwidth_constraint") is not None
            else base_bw,
            compute_constraint=_to_level(data.get("compute_constraint"), base_compute)
            if data.get("compute_constraint") is not None
            else base_compute,
            memory_constraint=_to_level(data.get("memory_constraint"), base_mem)
            if data.get("memory_constraint") is not None
            else base_mem,
            battery_constraint=_to_level(data.get("battery_constraint"), base_battery)
            if data.get("battery_constraint") is not None
            else base_battery,
            offline_operation=data["offline_operation"]
            if "offline_operation" in data and data["offline_operation"] is not None
            else (base.offline_operation if base else None),
            signature_frequency=data.get("signature_frequency")
            or (base.signature_frequency if base else None),
            verification_frequency=data.get("verification_frequency")
            or (base.verification_frequency if base else None),
            payload_size_sensitivity=_to_level(data.get("payload_size_sensitivity"), base_payload)
            if data.get("payload_size_sensitivity") is not None
            else base_payload,
            data_longevity=data.get("data_longevity")
            or (base.data_longevity if base else None),
            regulatory_requirements=tuple(
                data.get("regulatory_requirements")
                or (base.regulatory_requirements if base else ())
            ),
            platform_constraints=tuple(
                data.get("platform_constraints") or (base.platform_constraints if base else ())
            ),
            interoperability_constraints=tuple(
                data.get("interoperability_constraints")
                or (base.interoperability_constraints if base else ())
            ),
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
