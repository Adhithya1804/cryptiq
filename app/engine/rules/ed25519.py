from __future__ import annotations

import ast
from typing import Any

from app.engine.models import AnalysisContext, RawObservation, RuleMatch
from app.engine.rules.base import CryptoRule

ED25519_CLASSES = {
    "Ed25519PrivateKey",
    "Ed25519PublicKey",
}

KNOWN_ED25519_RECEIVERS = {
    "Ed25519PrivateKey",
    "Ed25519PublicKey",
    "ed25519_private_key",
    "ed25519_public_key",
    "ed25519_key",
}


class Ed25519Rule(CryptoRule):
    """
    Deterministic AST rule detecting explicit Ed25519 cryptographic semantics.
    Inspects Call and Attribute nodes for Ed25519PrivateKey and Ed25519PublicKey APIs
    (e.g., Ed25519PrivateKey.generate, .sign, .verify, .from_private_bytes, .from_public_bytes).
    Defends against generic .sign()/.verify() false positives using symbol tracking and receiver inspection.
    """

    rule_id: str = "PY-CRYPTO-ED25519"

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

        # 1. Ed25519 Key Generation: Ed25519PrivateKey.generate()
        if method_name == "generate":
            if self._is_ed25519_class(receiver, "Ed25519PrivateKey", context):
                return self._create_match(
                    call_node=call_node,
                    context=context,
                    api="Ed25519PrivateKey.generate",
                    operation="KEYGEN",
                )

        # 2. Key deserialization: from_private_bytes / from_public_bytes
        elif method_name == "from_private_bytes":
            if self._is_ed25519_class(receiver, "Ed25519PrivateKey", context):
                return self._create_match(
                    call_node=call_node,
                    context=context,
                    api="Ed25519PrivateKey.from_private_bytes",
                    operation="KEY_LOAD",
                )

        elif method_name == "from_public_bytes":
            if self._is_ed25519_class(receiver, "Ed25519PublicKey", context):
                return self._create_match(
                    call_node=call_node,
                    context=context,
                    api="Ed25519PublicKey.from_public_bytes",
                    operation="KEY_LOAD",
                )

        # 3. Ed25519 Digital Signature: private_key.sign(data)
        elif method_name == "sign":
            if self._is_ed25519_private_receiver(receiver, context):
                return self._create_match(
                    call_node=call_node,
                    context=context,
                    api="Ed25519PrivateKey.sign",
                    operation="SIGN",
                )

        # 4. Ed25519 Verification: public_key.verify(signature, data)
        elif method_name == "verify":
            if self._is_ed25519_public_receiver(receiver, context):
                return self._create_match(
                    call_node=call_node,
                    context=context,
                    api="Ed25519PublicKey.verify",
                    operation="VERIFY",
                )

        return None

    def _is_ed25519_class(self, node: ast.AST, class_name: str, context: AnalysisContext) -> bool:
        """
        Check if an AST node is the exact Ed25519 class or qualified attribute (e.g. ed25519.Ed25519PrivateKey).
        """
        if isinstance(node, ast.Name):
            if node.id == class_name:
                return True
            imported = context.imports.get(node.id, "")
            if class_name in imported or "ed25519" in imported:
                return True
        elif isinstance(node, ast.Attribute):
            if node.attr == class_name:
                return True
        return False

    def _is_ed25519_private_receiver(self, node: ast.AST, context: AnalysisContext) -> bool:
        """
        Check if the receiver node is established as an Ed25519 private key.
        Handles direct class reference, chained calls (.generate().sign()), and tracked variable assignments.
        """
        # Chained call: Ed25519PrivateKey.generate().sign(...)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if node.func.attr == "generate" and self._is_ed25519_class(node.func.value, "Ed25519PrivateKey", context):
                return True

        if isinstance(node, ast.Name):
            if node.id == "Ed25519PrivateKey" or node.id in KNOWN_ED25519_RECEIVERS:
                return True
            if node.id in context.symbol_table:
                origin = context.symbol_table[node.id]
                return self._is_ed25519_private_receiver(origin, context)
        elif isinstance(node, ast.Attribute):
            if node.attr == "Ed25519PrivateKey" or node.attr in KNOWN_ED25519_RECEIVERS:
                return True
        return False

    def _is_ed25519_public_receiver(self, node: ast.AST, context: AnalysisContext) -> bool:
        """
        Check if the receiver node is established as an Ed25519 public key.
        Handles chained calls (private_key.public_key().verify(...)) and tracked variables.
        """
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if node.func.attr == "public_key":
                return self._is_ed25519_private_receiver(node.func.value, context)
            if node.func.attr == "from_public_bytes":
                return self._is_ed25519_class(node.func.value, "Ed25519PublicKey", context)

        if isinstance(node, ast.Name):
            if node.id == "Ed25519PublicKey" or node.id in KNOWN_ED25519_RECEIVERS:
                return True
            if node.id in context.symbol_table:
                origin = context.symbol_table[node.id]
                return self._is_ed25519_public_receiver(origin, context)
        elif isinstance(node, ast.Attribute):
            if node.attr == "Ed25519PublicKey" or node.attr in KNOWN_ED25519_RECEIVERS:
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
            algorithm="Ed25519",
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
