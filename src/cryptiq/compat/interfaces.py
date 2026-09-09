"""Integration interfaces and domain contracts with Phases 1-8.

Provides clean protocol definitions and adapters so Phases 9-12 connect
seamlessly with the parser, rules, role engine, and source ingestion.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Protocol

from cryptiq.core.enums import ConfidenceLevel, CryptoRole, RetrievalMode


@dataclass
class SourceSnapshot:
    """Source code snapshot produced by Phase 3 ingestion."""
    provider: str
    owner: str
    repository: str
    commit_sha: str
    source_path: Path
    retrieval_mode: RetrievalMode = RetrievalMode.LIVE
    license_files: List[str] = field(default_factory=list)


@dataclass
class RuleMatch:
    """Cryptographic observation produced by Phases 5-8 rule and role evaluation."""
    rule_id: str
    algorithm: str
    api: str
    file_path: str
    start_line: int
    end_line: int
    confidence: ConfidenceLevel = ConfidenceLevel.CONFIRMED
    role: CryptoRole = CryptoRole.UNKNOWN
    pqc_guidance: str = "Review cryptographic usage for PQC migration"
    code_snippet: str = ""
    call_site: Optional[str] = None
    function_name: Optional[str] = None
    class_name: Optional[str] = None
    module_name: Optional[str] = None


@dataclass
class AnalysisResult:
    """Aggregated output from Phase 4-8 analysis pipeline."""
    files_analyzed: int = 0
    matches: List[RuleMatch] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)


class SourceProvider(Protocol):
    """Protocol for Phase 3 source ingestion."""

    def get_snapshot(
        self,
        provider: str,
        owner: str,
        repository: str,
        commit_sha: str,
    ) -> SourceSnapshot:
        ...


class AnalysisEngine(Protocol):
    """Protocol for Phases 4-8 detection and classification engine."""

    def analyze(self, snapshot: SourceSnapshot) -> AnalysisResult:
        ...
