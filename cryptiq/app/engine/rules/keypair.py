"""The shape shared by the key-class rules.

Ed25519, X25519 and RSA all work the same way: a module holds a private and a
public key class, a handful of constructors return one of them, and a small set
of methods on an established key is the operation. Only the names differ, so
the recognition lives here once and each rule supplies its own table.
"""

import ast
from collections.abc import Mapping
from dataclasses import dataclass

from app.engine.engine import engine_versions
from app.engine.rules.base import (
    AnalysisContext,
    Call,
    CryptoOperation,
    EvidenceBasis,
    MatchConfidence,
    RuleMatch,
)
from app.engine.rules.resolution import KeyKind, NamespaceSpec

LIBRARY = "cryptography"


@dataclass(frozen=True)
class KeyPairRule:
    """Recognises one key-class algorithm from the ``cryptography`` library.

    ``module_operations`` maps a member of the namespace -- a function, or a
    class method written as ``Class.method`` -- to the operation it performs.
    ``method_operations`` maps a method on an established key to its operation
    and to the half of the key pair it requires; a method on the wrong half is
    not reported, because the evidence contradicts itself.
    """

    rule_id: str
    algorithm: str
    primitive: str
    prefix: str
    spec: NamespaceSpec
    module_operations: Mapping[str, CryptoOperation]
    method_operations: Mapping[str, tuple[CryptoOperation, KeyKind]]
    canonical_class: Mapping[KeyKind, str]

    @property
    def version(self) -> str:
        """The configured rule set version, stamped on every match."""
        return engine_versions().ruleset_version

    def evaluate(self, node: ast.AST, context: AnalysisContext) -> RuleMatch | None:
        """Return an observation for a call node, or None."""
        call = context.call(node)
        if call is None or call.chain is None:
            return None
        return self._imported_api(call, context) or self._receiver_api(call, context)

    def _imported_api(self, call: Call, context: AnalysisContext) -> RuleMatch | None:
        """Match a call whose callable resolves into the algorithm's namespace."""
        member = self.spec.member(context.file, call.chain)
        if member is None:
            return None

        operation = self.module_operations.get(member)
        if operation is not None:
            return self._match(
                call,
                api=self._api(member),
                operation=operation,
                confidence=MatchConfidence.HIGH,
                basis=EvidenceBasis.DIRECT_MODULE_API,
            )

        class_name, _, method = member.partition(".")
        kind = self.spec.class_kind(class_name)
        entry = self.method_operations.get(method)
        if kind is None or entry is None or entry[1] is not kind:
            return None
        return self._match(
            call,
            api=f"{class_name}.{method}",
            operation=entry[0],
            confidence=MatchConfidence.HIGH,
            basis=EvidenceBasis.CLASS_IMPORT,
        )

    def _receiver_api(self, call: Call, context: AnalysisContext) -> RuleMatch | None:
        """Match a key method on a local name established as one of these keys."""
        if len(call.chain) != 2:
            return None
        entry = self.method_operations.get(call.chain[1])
        if entry is None:
            return None
        operation, required = entry

        binding = context.index(self.rule_id, self.spec).lookup(
            call.enclosing_function, call.chain[0]
        )
        if binding is None or binding.kind is not required:
            return None

        return self._match(
            call,
            api=f"{self.canonical_class[binding.kind]}.{call.chain[1]}",
            operation=operation,
            confidence=binding.confidence,
            basis=binding.basis,
        )

    def _api(self, member: str) -> str:
        """Name a namespace member the way a reader would write it."""
        return member if "." in member else f"{self.prefix}.{member}"

    def _match(
        self,
        call: Call,
        *,
        api: str,
        operation: CryptoOperation,
        confidence: MatchConfidence,
        basis: EvidenceBasis,
    ) -> RuleMatch:
        return RuleMatch(
            rule_id=self.rule_id,
            ruleset_version=self.version,
            algorithm=self.algorithm,
            primitive=self.primitive,
            library=LIBRARY,
            api=api,
            operation=operation,
            file_path=call.path,
            location=call.location,
            confidence=confidence,
            evidence_basis=basis,
            enclosing_function=call.enclosing_function,
            enclosing_class=call.enclosing_class,
            node=call.node,
        )
