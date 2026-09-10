"""The shape shared by the rules whose evidence is an algorithm argument.

Elliptic-curve keys do not say which algorithm they are used for; the call
does. ``key.sign(data, ec.ECDSA(...))`` is a signature and
``key.exchange(ec.ECDH(), peer)`` is a key agreement, and in both cases the
proof is the argument, not the receiver. That makes the receiver irrelevant:
an EC key of unknown provenance still signs with ECDSA when the ECDSA marker
is passed.
"""

import ast
from collections.abc import Mapping
from dataclasses import dataclass

from app.engine.engine import engine_versions
from app.engine.parser import CallArgument, ParsedFile, attribute_chain
from app.engine.rules.base import (
    AnalysisContext,
    Call,
    CryptoOperation,
    EvidenceBasis,
    MatchConfidence,
    RuleMatch,
)
from app.engine.rules.resolution import names_assigned_from, resolve_chain

LIBRARY = "cryptography"


@dataclass(frozen=True)
class MarkerRule:
    """Recognises an algorithm named as an argument to a key operation."""

    rule_id: str
    algorithm: str
    primitive: str
    marker: str
    method_operations: Mapping[str, CryptoOperation]

    @property
    def version(self) -> str:
        """The configured rule set version, stamped on every match."""
        return engine_versions().ruleset_version

    def evaluate(self, node: ast.AST, context: AnalysisContext) -> RuleMatch | None:
        """Return an observation for a call node, or None."""
        call = context.call(node)
        if call is None or call.attribute is None:
            return None
        operation = self.method_operations.get(call.attribute)
        if operation is None:
            return None

        confidence, basis = self._evidence(call, context)
        if confidence is None or basis is None:
            return None

        return RuleMatch(
            rule_id=self.rule_id,
            ruleset_version=self.version,
            algorithm=self.algorithm,
            primitive=self.primitive,
            library=LIBRARY,
            api=f"{self.algorithm}.{call.attribute}",
            operation=operation,
            file_path=call.path,
            location=call.location,
            confidence=confidence,
            evidence_basis=basis,
            enclosing_function=call.enclosing_function,
            enclosing_class=call.enclosing_class,
            node=call.node,
        )

    def _evidence(
        self, call: Call, context: AnalysisContext
    ) -> tuple[MatchConfidence | None, EvidenceBasis | None]:
        """Return how firmly an argument names this algorithm."""
        for argument in call.arguments:
            if self._is_direct_marker(argument, context.file):
                return MatchConfidence.HIGH, EvidenceBasis.DIRECT_MODULE_API

        assigned = context.cached(f"{self.rule_id}:names", self._assigned_names)
        for argument in call.arguments:
            name = argument.expression
            if name is None or not name.isidentifier():
                continue
            if assigned.get((call.enclosing_function, name)):
                return MatchConfidence.MEDIUM, EvidenceBasis.CONSTRUCTOR_ASSIGNMENT

        return None, None

    def _is_direct_marker(self, argument: CallArgument, file: ParsedFile) -> bool:
        """True when the argument is a call to the marker written in place."""
        if not isinstance(argument.node, ast.Call):
            return False
        return resolve_chain(file, attribute_chain(argument.node.func)) == self.marker

    def _assigned_names(self, file: ParsedFile) -> dict[tuple[str | None, str], bool]:
        return names_assigned_from(file, self.marker)
