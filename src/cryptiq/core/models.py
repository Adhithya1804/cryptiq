"""Core domain models for Cryptiq."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

from cryptiq.core.enums import (
    ConfidenceLevel,
    CryptoRole,
    ImpactNodeType,
    ImpactRelationship,
    ImpactScope,
    JobStatus,
    PriorityLevel,
    RetrievalMode,
    ScanStatus,
)


@dataclass
class Evidence:
    """Source-backed evidence for a cryptographic finding."""
    file_path: str
    line_start: int
    line_end: int
    code_snippet: str
    confidence: ConfidenceLevel = ConfidenceLevel.CONFIRMED
    symbol: Optional[str] = None
    call_site: Optional[str] = None
    function_name: Optional[str] = None
    class_name: Optional[str] = None
    module_name: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["confidence"] = self.confidence.value
        return data


@dataclass
class ImpactNode:
    """A node in the bounded impact graph."""
    id: str
    finding_id: str
    node_type: ImpactNodeType
    label: str
    relationship: Optional[ImpactRelationship] = None
    confidence: ConfidenceLevel = ConfidenceLevel.CONFIRMED

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "finding_id": self.finding_id,
            "node_type": self.node_type.value,
            "label": self.label,
            "relationship": self.relationship.value if self.relationship else None,
            "confidence": self.confidence.value,
        }


@dataclass
class ImpactEdge:
    """A directed edge in the bounded impact graph."""
    source_id: str
    target_id: str
    relationship: ImpactRelationship
    confidence: ConfidenceLevel = ConfidenceLevel.CONFIRMED

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source_id": self.source_id,
            "target_id": self.target_id,
            "relationship": self.relationship.value,
            "confidence": self.confidence.value,
        }


@dataclass
class ImpactResult:
    """Result of bounded static impact analysis."""
    scope: ImpactScope
    nodes: List[ImpactNode] = field(default_factory=list)
    relationships: List[ImpactEdge] = field(default_factory=list)
    confidence: ConfidenceLevel = ConfidenceLevel.CONFIRMED

    def to_dict(self) -> Dict[str, Any]:
        return {
            "scope": self.scope.value,
            "nodes": [n.to_dict() for n in self.nodes],
            "relationships": [r.to_dict() for r in self.relationships],
            "confidence": self.confidence.value,
        }


@dataclass
class PriorityResult:
    """Result of deterministic Migration Review Priority scoring."""
    level: PriorityLevel
    reasons: List[str] = field(default_factory=list)
    score: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "level": self.level.value,
            "reasons": list(self.reasons),
            "score": self.score,
        }


@dataclass
class Finding:
    """A cryptographic usage observation with source evidence, role, impact, and priority."""
    id: str
    scan_id: str
    repository: str
    commit_sha: str
    file_path: str
    start_line: int
    end_line: int
    rule_id: str
    algorithm: str
    api: str
    confidence: ConfidenceLevel
    role: CryptoRole
    pqc_guidance: str
    priority: PriorityLevel
    priority_reasons: List[str] = field(default_factory=list)
    fingerprint: str = ""
    evidence: Optional[Evidence] = None
    impact: Optional[ImpactResult] = None
    created_at: Optional[datetime] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "scan_id": self.scan_id,
            "repository": self.repository,
            "commit_sha": self.commit_sha,
            "file_path": self.file_path,
            "start_line": self.start_line,
            "end_line": self.end_line,
            "rule_id": self.rule_id,
            "algorithm": self.algorithm,
            "api": self.api,
            "confidence": self.confidence.value,
            "role": self.role.value,
            "pqc_guidance": self.pqc_guidance,
            "priority": self.priority.value,
            "priority_reasons": self.priority_reasons,
            "fingerprint": self.fingerprint,
            "evidence": self.evidence.to_dict() if self.evidence else None,
            "impact": self.impact.to_dict() if self.impact else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


@dataclass
class Scan:
    """A scan record representing one repository snapshot analysis."""
    id: str
    provider: str
    owner: str
    repository: str
    commit_sha: str
    parser_version: str
    ruleset_version: str
    pqc_ruleset_version: str
    status: ScanStatus = ScanStatus.QUEUED
    retrieval_mode: RetrievalMode = RetrievalMode.LIVE
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    file_count: int = 0
    finding_count: int = 0
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    created_at: Optional[datetime] = None

    @property
    def identity_tuple(self) -> tuple[str, str, str, str, str, str, str]:
        """Canonical 7-part scan identity tuple."""
        return (
            self.provider,
            self.owner,
            self.repository,
            self.commit_sha,
            self.parser_version,
            self.ruleset_version,
            self.pqc_ruleset_version,
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "provider": self.provider,
            "owner": self.owner,
            "repository": self.repository,
            "commit_sha": self.commit_sha,
            "parser_version": self.parser_version,
            "ruleset_version": self.ruleset_version,
            "pqc_ruleset_version": self.pqc_ruleset_version,
            "status": self.status.value,
            "retrieval_mode": self.retrieval_mode.value,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "file_count": self.file_count,
            "finding_count": self.finding_count,
            "error_code": self.error_code,
            "error_message": self.error_message,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


@dataclass
class ScanJob:
    """Asynchronous job representation for scan execution."""
    id: str
    scan_id: str
    status: JobStatus = JobStatus.QUEUED
    attempt_count: int = 0
    max_attempts: int = 3
    locked_at: Optional[datetime] = None
    locked_by: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    last_error: Optional[str] = None
    created_at: Optional[datetime] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "scan_id": self.scan_id,
            "status": self.status.value,
            "attempt_count": self.attempt_count,
            "max_attempts": self.max_attempts,
            "locked_at": self.locked_at.isoformat() if self.locked_at else None,
            "locked_by": self.locked_by,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "last_error": self.last_error,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
