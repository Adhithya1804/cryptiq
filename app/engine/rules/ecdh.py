from __future__ import annotations

import ast
from typing import Any

from app.engine.models import AnalysisContext, RawObservation, RuleMatch
from app.engine.rules.base import CryptoRule


class ECDHRule(CryptoRule):
    """
    Deterministic AST rule detecting explicit ECDH key agreement semantics.
    Inspects Call nodes for .exchange(ec.ECDH(), peer_public_key) on elliptic curve private keys.
    Strictly avoids false positives on generic .exchange() methods by requiring explicit ECDH algorithm arguments.
    """

    rule_id: str = "PY-CRYPTO-ECDH"

    def evaluate(
        self,
        node: ast.AST,
        context: AnalysisContext,
    ) -> RuleMatch | None:
        if not isinstance(node, ast.Call):
            return None

        if isinstance(node.func, ast.Attribute) and node.func.attr == "exchange":
            return self._evaluate_exchange_call(node, node.func, context)

        return None

    def _evaluate_exchange_call(
        self,
        call_node: ast.Call,
        func_node: ast.Attribute,
        context: AnalysisContext,
    ) -> RuleMatch | None:
        receiver = func_node.value

        # In cryptography: private_key.exchange(ec.ECDH(), peer_public_key)
        # Check if any argument is an instantiation or reference of ECDH
        has_ecdh_arg = False
        for arg in call_node.args:
            if self._is_ecdh_algorithm_node(arg, context):
                has_ecdh_arg = True
                break

        for kw in call_node.keywords:
            if kw.arg in ("algorithm", "ecdh") and self._is_ecdh_algorithm_node(kw.value, context):
                has_ecdh_arg = True
                break

        # Check receiver context if receiver is known EC private key
        is_ec_receiver = self._is_ec_private_key(receiver, context)

        # Match when ECDH argument is explicitly present, or receiver is explicitly an EC private key with exchange
        if has_ecdh_arg or (is_ec_receiver and len(call_node.args) >= 1):
            return self._create_match(
                call_node=call_node,
                context=context,
                api="ECDH.exchange",
                operation="KEY_EXCHANGE",
            )

        return None

    def _is_ecdh_algorithm_node(self, node: ast.AST, context: AnalysisContext) -> bool:
        """
        Detect ec.ECDH() or ECDH() call/attribute.
        """
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Attribute) and node.func.attr == "ECDH":
                return True
            elif isinstance(node.func, ast.Name) and node.func.id == "ECDH":
                return True
        elif isinstance(node, ast.Attribute) and node.attr == "ECDH":
            return True
        elif isinstance(node, ast.Name):
            if node.id == "ECDH":
                return True
            if node.id in context.symbol_table:
                sym_val = context.symbol_table[node.id]
                if isinstance(sym_val, ast.AST):
                    return self._is_ecdh_algorithm_node(sym_val, context)
        return False

    def _is_ec_private_key(self, node: ast.AST, context: AnalysisContext) -> bool:
        """
        Check if receiver node resolves to EllipticCurvePrivateKey.
        """
        if isinstance(node, ast.Name):
            if node.id in ("EllipticCurvePrivateKey", "ec_private_key"):
                return True
            if node.id in context.symbol_table:
                origin = context.symbol_table[node.id]
                if isinstance(origin, ast.Call) and isinstance(origin.func, ast.Attribute):
                    return origin.func.attr == "generate_private_key" and self._is_ec_module(origin.func.value, context)
                if isinstance(origin, ast.Call) and isinstance(origin.func, ast.Name):
                    if origin.func.id == "generate_private_key":
                        imported = context.imports.get("generate_private_key", "")
                        return "asymmetric.ec" in imported or imported.endswith(".ec")
        elif isinstance(node, ast.Attribute):
            return node.attr in ("EllipticCurvePrivateKey", "ec_private_key")
        return False

    def _is_ec_module(self, node: ast.AST, context: AnalysisContext) -> bool:
        """
        Check if an AST node refers specifically to the ec module.
        Must NOT match other cryptography submodules (rsa, ed25519, x25519).
        """
        if isinstance(node, ast.Name):
            if node.id == "ec":
                return True
            imported = context.imports.get(node.id, "")
            if "asymmetric.ec" in imported or imported.endswith(".ec"):
                return True
        elif isinstance(node, ast.Attribute):
            if node.attr == "ec":
                return True
        return False

    def _create_match(
        self,
        call_node: ast.Call,
        context: AnalysisContext,
        api: str,
        operation: str,
    ) -> RuleMatch:
        start_line = getattr(call_node, "lineno", 1)
        end_line = getattr(call_node, "end_lineno", start_line)
        col_offset = getattr(call_node, "col_offset", 0)
        end_col_offset = getattr(call_node, "end_col_offset", None)

        observation = RawObservation(
            algorithm="ECDH",
            library="cryptography",
            api=api,
            operation=operation,
            primitive="ASYMMETRIC",
            metadata={},
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
