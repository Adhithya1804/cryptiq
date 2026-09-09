from __future__ import annotations

import ast
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class CryptoRole(str, Enum):
    """
    Standardized cryptographic role taxonomy according to Cryptiq specification.
    Strictly separates inferred functional role from observed primitive algorithm.
    """
    DIGITAL_SIGNATURE = "DIGITAL_SIGNATURE"
    KEY_ESTABLISHMENT = "KEY_ESTABLISHMENT"
    SYMMETRIC_ENCRYPTION = "SYMMETRIC_ENCRYPTION"
    HASH = "HASH"
    PROTOCOL = "PROTOCOL"
    UNKNOWN = "UNKNOWN"


class Confidence(str, Enum):
    """
    Confidence rating for inferred cryptographic roles.
    """
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    UNKNOWN = "UNKNOWN"


@dataclass
class RoleInference:
    """
    Inferred role for a raw cryptographic observation with associated confidence level.
    Captures deterministic derivation rationale and hierarchy tier.
    """
    role: CryptoRole
    confidence: Confidence
    reasoning: str = ""
    hierarchy_level: str = "EXPLICIT_API"


@dataclass
class MigrationPath:
    """
    Recommended post-quantum cryptography migration review path.
    Derived deterministically from algorithm + role combination.
    """
    review_path: list[str] = field(default_factory=list)
    pqc_ruleset_version: str = "0.1.0"
    notes: str = ""

    @property
    def display_path(self) -> str:
        """Formatted display string, e.g. 'ML-DSA / SLH-DSA'."""
        return " / ".join(self.review_path) if self.review_path else "Manual review"

    def __contains__(self, item: object) -> bool:
        if isinstance(item, str):
            return item in self.review_path or item == self.display_path
        return False

    def __eq__(self, other: object) -> bool:
        if isinstance(other, MigrationPath):
            return (
                self.review_path == other.review_path
                and self.pqc_ruleset_version == other.pqc_ruleset_version
            )
        elif isinstance(other, list):
            return self.review_path == other
        elif isinstance(other, str):
            return self.display_path == other or other in self.review_path
        return False

    def __hash__(self) -> int:
        return hash((tuple(self.review_path), self.pqc_ruleset_version))


@dataclass
class RawObservation:
    """
    Deterministic cryptographic fact observed directly at an AST node.
    Strictly separates observed facts from downstream inferred roles.
    """
    algorithm: str
    library: str
    api: str
    operation: str
    primitive: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class RuleMatch:
    """
    Result of a pure rule evaluation matching an AST node.
    Binds the matched AST node to its raw observation and file boundaries.
    """
    rule_id: str
    node: ast.AST
    observation: RawObservation
    file_path: str = ""
    start_line: int = 0
    end_line: int = 0
    col_offset: int = 0
    end_col_offset: int | None = None


@dataclass
class Evidence:
    """
    Immutable evidence record capturing the exact source location and excerpt.
    A finding without evidence cannot exist in Cryptiq.
    """
    file_path: str
    start_line: int
    end_line: int
    col_offset: int
    end_col_offset: int | None = None
    source_excerpt: str = ""
    rule_id: str | None = None
    repository_sha: str | None = None


@dataclass
class ParsedFile:
    """
    Representation of a parsed source file containing symbol tables and AST references.
    """
    path: str = ""
    language: str = "python"
    imports: dict[str, str] = field(default_factory=dict)
    symbols: dict[str, Any] = field(default_factory=dict)
    calls: list[Any] = field(default_factory=list)
    ast: Any | None = None
    source_lines: list[str] = field(default_factory=list)
    source_code: str = ""


@dataclass
class AnalysisContext:
    """
    Context passed to rules during AST traversal.
    Provides immutable source references, import mappings, and symbol resolution.
    Never executes or imports target repository code.
    """
    file_path: str = ""
    source_code: str = ""
    source_lines: list[str] = field(default_factory=list)
    imports: dict[str, str] = field(default_factory=dict)
    symbol_table: dict[str, Any] = field(default_factory=dict)
    parent_map: dict[int, ast.AST] = field(default_factory=dict)

    @classmethod
    def from_source(cls, source_code: str, file_path: str = "") -> AnalysisContext:
        """
        Build an AnalysisContext from source code deterministically using ast traversal.
        """
        lines = source_code.splitlines()
        ctx = cls(
            file_path=file_path,
            source_code=source_code,
            source_lines=lines,
        )

        try:
            tree = ast.parse(source_code, filename=file_path or "<unknown>")
        except SyntaxError:
            # If the source file has syntax errors, return base context with raw lines intact
            return ctx

        # Deterministically collect imports, parent relationships, and assignments
        for parent in ast.walk(tree):
            for child in ast.iter_child_nodes(parent):
                ctx.parent_map[id(child)] = parent

            if isinstance(parent, ast.Import):
                for alias in parent.names:
                    name_key = alias.asname if alias.asname else alias.name
                    ctx.imports[name_key] = alias.name
            elif isinstance(parent, ast.ImportFrom):
                module = parent.module or ""
                for alias in parent.names:
                    name_key = alias.asname if alias.asname else alias.name
                    full_path = f"{module}.{alias.name}" if module else alias.name
                    ctx.imports[name_key] = full_path
            elif isinstance(parent, ast.Assign):
                # Track assignments such as: private_key = rsa.generate_private_key(...)
                for target in parent.targets:
                    if isinstance(target, ast.Name):
                        ctx.symbol_table[target.id] = parent.value
            elif isinstance(parent, ast.AnnAssign):
                # Track annotated assignments: private_key: RSAPrivateKey = ...
                if isinstance(parent.target, ast.Name):
                    ctx.symbol_table[parent.target.id] = parent.annotation

        return ctx


@dataclass
class FindingResult:
    """
    Unified cryptographic finding matching Section 51 of the Master Specification.
    Binds observed facts, immutable evidence, inferred role, and PQC migration path.
    Impact, priority, and fingerprint fields are provided for Phase 9-12 integration.
    """
    observed: RawObservation
    evidence: Evidence
    role: RoleInference
    migration: MigrationPath
    impact: Any | None = None
    priority: Any | None = None
    fingerprint: str | None = None


@dataclass
class AnalysisResult:
    """
    Aggregate result of the Analysis Engine pipeline matching Section 51.
    """
    findings: list[FindingResult] = field(default_factory=list)
    manifest: dict[str, Any] = field(default_factory=dict)

