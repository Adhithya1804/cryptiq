"""The rule interface and the raw observation a rule produces.

A rule reports what it can establish from syntax, and nothing more. It does
not decide a cryptographic role, an impact or a priority; later stages do
that. A rule that cannot establish its claim reports nothing at all, because a
false finding costs a reviewer more than a missed one.
"""

import ast
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Protocol

from app.engine.parser import Call, ParsedFile, SourceLocation


class CryptoOperation(StrEnum):
    """What a detected construct does.

    ENCRYPT and DECRYPT cover both asymmetric and symmetric use; the algorithm
    on the match says which. CONSTRUCTION is for building a primitive that is
    not itself an operation on data, such as naming a cipher algorithm.
    """

    KEY_GENERATION = "KEY_GENERATION"
    KEY_ESTABLISHMENT = "KEY_ESTABLISHMENT"
    SIGN = "SIGN"
    VERIFY = "VERIFY"
    ENCRYPT = "ENCRYPT"
    DECRYPT = "DECRYPT"
    CONSTRUCTION = "CONSTRUCTION"
    HASH = "HASH"


class MatchConfidence(StrEnum):
    """How firmly the syntax establishes the claim.

    UNKNOWN exists for completeness; no rule emits it, because a match that
    cannot be established is not reported.
    """

    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    UNKNOWN = "UNKNOWN"


class EvidenceBasis(StrEnum):
    """Which form of syntactic evidence produced a match.

    Recorded so a match can be explained and audited without re-running the
    rule. The values are fixed strings, never generated text.
    """

    DIRECT_MODULE_API = "DIRECT_MODULE_API"
    CLASS_IMPORT = "CLASS_IMPORT"
    CLASS_ANNOTATION = "CLASS_ANNOTATION"
    CONSTRUCTOR_ASSIGNMENT = "CONSTRUCTOR_ASSIGNMENT"
    ESTABLISHED_ALIAS = "ESTABLISHED_ALIAS"


@dataclass(frozen=True)
class RuleMatch:
    """One raw cryptographic observation, before any interpretation."""

    rule_id: str
    ruleset_version: str
    algorithm: str
    primitive: str
    library: str
    api: str
    operation: CryptoOperation
    file_path: str
    location: SourceLocation
    confidence: MatchConfidence
    evidence_basis: EvidenceBasis
    enclosing_function: str | None = None
    enclosing_class: str | None = None
    node: ast.AST | None = field(default=None, compare=False, repr=False)

    @property
    def sort_key(self) -> tuple[str, int, int, str, str, str]:
        """The total order used wherever matches are collected."""
        return (
            self.file_path,
            self.location.start_line,
            self.location.start_column,
            self.rule_id,
            self.api,
            self.operation.value,
        )


@dataclass
class AnalysisContext:
    """What a rule sees while evaluating one file.

    ``cache`` lets a rule keep per-file work, such as an index of which local
    names hold which kind of key, instead of rebuilding it for every call.
    """

    file: ParsedFile
    _calls: dict[int, Call] = field(default_factory=dict, init=False, repr=False)
    cache: dict[str, Any] = field(default_factory=dict, repr=False)

    def __post_init__(self) -> None:
        self._calls = {id(call.node): call for call in self.file.calls}

    def call(self, node: ast.AST) -> Call | None:
        """Return the parsed call for a node of this file, if it is one."""
        return self._calls.get(id(node))

    def index(self, rule_id: str, spec: Any) -> Any:
        """Return this rule's binding index for the file, building it once."""
        from app.engine.rules.resolution import build_index

        cached = self.cache.get(rule_id)
        if cached is None:
            cached = build_index(self.file, spec)
            self.cache[rule_id] = cached
        return cached

    def cached(self, key: str, build: Any) -> Any:
        """Return a per-file value a rule computes once, building it on demand."""
        value = self.cache.get(key)
        if value is None:
            value = build(self.file)
            self.cache[key] = value
        return value


class CryptoRule(Protocol):
    """Recognises one family of cryptographic API usage."""

    rule_id: str

    def evaluate(self, node: ast.AST, context: AnalysisContext) -> RuleMatch | None:
        """Return an observation for this node, or None when nothing is established."""
        ...
