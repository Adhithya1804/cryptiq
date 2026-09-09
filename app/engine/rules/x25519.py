from __future__ import annotations

import ast
from typing import Any

from app.engine.models import AnalysisContext, RawObservation, RuleMatch
from app.engine.rules.base import CryptoRule

KNOWN_X25519_RECEIVERS = {
    "X25519PrivateKey",
    "X25519PublicKey",
    "x25519_private_key",
    "x25519_public_key",
    "x25519_key",
}


class X25519Rule(CryptoRule):
    """
    Deterministic AST rule detecting explicit X25519 cryptographic semantics.
    Inspects Call and Attribute nodes for X25519PrivateKey and X25519PublicKey APIs
    (e.g., X25519PrivateKey.generate, .exchange, .from_private_bytes, .from_public_bytes).
    Avoids false positives on generic .exchange() methods by requiring verified X25519 receiver context.
    """

    rule_id: str = "PY-CRYPTO-X25519"

    def evaluate(
        self,
        node: ast.AST,
        context: AnalysisContext,
    ) -> RuleMatch | None:
        if not isinstance(node, ast.Call):
            return None

        if isinstance(node.func, ast.Attribute):
            return self._evaluate_attribute_call(node, node.func, context)

        return None

    def _evaluate_attribute_call(
        self,
        call_node: ast.Call,
        func_node: ast.Attribute,
        context: AnalysisContext,
    ) -> RuleMatch | None:
        method_name = func_node.attr
        receiver = func_node.value

        # 1. Key Generation: X25519PrivateKey.generate()
        if method_name == "generate":
            if self._is_x25519_class(receiver, "X25519PrivateKey", context):
                return self._create_match(
                    call_node=call_node,
                    context=context,
                    api="X25519PrivateKey.generate",
                    operation="KEYGEN",
                )

        # 2. Key Exchange: private_key.exchange(peer_public_key)
        # Specifically handles chained: X25519PrivateKey.generate().exchange(...)
        elif method_name == "exchange":
            if self._is_x25519_private_receiver(receiver, context):
                return self._create_match(
                    call_node=call_node,
                    context=context,
                    api="X25519PrivateKey.exchange",
                    operation="KEY_EXCHANGE",
                )

        # 3. Key Deserialization: from_private_bytes / from_public_bytes
        elif method_name == "from_private_bytes":
            if self._is_x25519_class(receiver, "X25519PrivateKey", context):
                return self._create_match(
                    call_node=call_node,
                    context=context,
                    api="X25519PrivateKey.from_private_bytes",
                    operation="KEY_LOAD",
                )

        elif method_name == "from_public_bytes":
            if self._is_x25519_class(receiver, "X25519PublicKey", context):
                return self._create_match(
                    call_node=call_node,
                    context=context,
                    api="X25519PublicKey.from_public_bytes",
                    operation="KEY_LOAD",
                )

        return None

    def _is_x25519_class(self, node: ast.AST, class_name: str, context: AnalysisContext) -> bool:
        """
        Check if an AST node is the exact X25519 class or qualified attribute (e.g., x25519.X25519PrivateKey).
        """
        if isinstance(node, ast.Name):
            if node.id == class_name:
                return True
            imported = context.imports.get(node.id, "")
            if class_name in imported or "x25519" in imported:
                return True
        elif isinstance(node, ast.Attribute):
            if node.attr == class_name:
                return True
        return False

    def _is_x25519_private_receiver(self, node: ast.AST, context: AnalysisContext) -> bool:
        """
        Check if the receiver node is established as an X25519 private key.
        Explicitly handles chained calls (e.g. X25519PrivateKey.generate().exchange()) and symbol references.
        """
        # Chained call: X25519PrivateKey.generate().exchange(...)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if node.func.attr == "generate" and self._is_x25519_class(node.func.value, "X25519PrivateKey", context):
                return True

        if isinstance(node, ast.Name):
            if node.id == "X25519PrivateKey" or node.id in KNOWN_X25519_RECEIVERS:
                return True
            if node.id in context.symbol_table:
                origin = context.symbol_table[node.id]
                return self._is_x25519_private_receiver(origin, context)
        elif isinstance(node, ast.Attribute):
            if node.attr == "X25519PrivateKey" or node.attr in KNOWN_X25519_RECEIVERS:
                return True
        return False

    def _create_match(
        self,
        call_node: ast.Call,
        context: AnalysisContext,
        api: str,
        operation: str,
        metadata: dict[str, Any] | None = None,
    ) -> RuleMatch:
        start_line = getattr(call_node, "lineno", 1)
        end_line = getattr(call_node, "end_lineno", start_line)
        col_offset = getattr(call_node, "col_offset", 0)
        end_col_offset = getattr(call_node, "end_col_offset", None)

        observation = RawObservation(
            algorithm="X25519",
            library="cryptography",
            api=api,
            operation=operation,
            primitive="ASYMMETRIC",
            metadata=metadata or {},
        )

        return RuleMatch(
            rule_id=self.rule_id,
            node=call_node,
            observation=observation,
            file_path=context.file_path,
            start_line=start_line,
            end_line=end_line,
            col_offset=col_offset,
            end_col_offset=end_col_offset,
        )
