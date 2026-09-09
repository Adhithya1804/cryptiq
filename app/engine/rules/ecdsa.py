from __future__ import annotations

import ast
from typing import Any

from app.engine.models import AnalysisContext, RawObservation, RuleMatch
from app.engine.rules.base import CryptoRule

KNOWN_EC_RECEIVERS = {
    "EllipticCurvePrivateKey",
    "EllipticCurvePublicKey",
    "ec_private_key",
    "ec_public_key",
    "ec_key",
}


class ECDSARule(CryptoRule):
    """
    Deterministic AST rule detecting explicit ECDSA cryptographic semantics.
    Inspects Call and Attribute nodes for cryptography library ECDSA APIs
    (e.g., EllipticCurvePrivateKey.sign with ec.ECDSA, EllipticCurvePublicKey.verify, ec.generate_private_key).
    """

    rule_id: str = "PY-CRYPTO-ECDSA"

    def evaluate(
        self,
        node: ast.AST,
        context: AnalysisContext,
    ) -> RuleMatch | None:
        """
        Pure evaluation of an AST node for ECDSA semantics.
        """
        if not isinstance(node, ast.Call):
            return None

        # Case 1: Method call on an object
        if isinstance(node.func, ast.Attribute):
            return self._evaluate_attribute_call(node, node.func, context)

        # Case 2: Directly imported function call
        elif isinstance(node.func, ast.Name):
            return self._evaluate_name_call(node, node.func, context)

        return None

    def _evaluate_attribute_call(
        self,
        call_node: ast.Call,
        func_node: ast.Attribute,
        context: AnalysisContext,
    ) -> RuleMatch | None:
        method_name = func_node.attr
        receiver = func_node.value

        # 1. EC Key Generation: ec.generate_private_key(curve, ...)
        if method_name == "generate_private_key":
            if self._is_ec_module(receiver, context):
                metadata = self._extract_keygen_metadata(call_node)
                return self._create_match(
                    call_node=call_node,
                    context=context,
                    api="ec.generate_private_key",
                    operation="KEYGEN",
                    metadata=metadata,
                )

        # 2. ECDSA Signature: private_key.sign(data, ec.ECDSA(...))
        elif method_name == "sign":
            is_ecdsa, hash_name = self._check_ecdsa_signature_args(call_node, receiver, context)
            if is_ecdsa:
                metadata: dict[str, Any] = {}
                if hash_name:
                    metadata["hash_algorithm"] = hash_name
                return self._create_match(
                    call_node=call_node,
                    context=context,
                    api="EllipticCurvePrivateKey.sign",
                    operation="SIGN",
                    metadata=metadata,
                )

        # 3. ECDSA Verification: public_key.verify(signature, data, ec.ECDSA(...))
        elif method_name == "verify":
            is_ecdsa, hash_name = self._check_ecdsa_verify_args(call_node, receiver, context)
            if is_ecdsa:
                metadata: dict[str, Any] = {}
                if hash_name:
                    metadata["hash_algorithm"] = hash_name
                return self._create_match(
                    call_node=call_node,
                    context=context,
                    api="EllipticCurvePublicKey.verify",
                    operation="VERIFY",
                    metadata=metadata,
                )

        return None

    def _evaluate_name_call(
        self,
        call_node: ast.Call,
        func_node: ast.Name,
        context: AnalysisContext,
    ) -> RuleMatch | None:
        if func_node.id == "generate_private_key":
            imported_from = context.imports.get("generate_private_key", "")
            if "asymmetric.ec" in imported_from or imported_from.endswith(".ec"):
                metadata = self._extract_keygen_metadata(call_node)
                return self._create_match(
                    call_node=call_node,
                    context=context,
                    api="ec.generate_private_key",
                    operation="KEYGEN",
                    metadata=metadata,
                )
        return None

    def _check_ecdsa_signature_args(
        self,
        call_node: ast.Call,
        receiver: ast.AST,
        context: AnalysisContext,
    ) -> tuple[bool, str | None]:
        """
        Check if call has ec.ECDSA argument or receiver is an EllipticCurvePrivateKey.
        In cryptography: sign(data, signature_algorithm) where signature_algorithm is ec.ECDSA(hash).
        """
        sig_algo_node = self._get_arg_or_keyword(call_node, 1, "signature_algorithm")
        if sig_algo_node is not None:
            is_ecdsa, hash_name = self._inspect_ecdsa_algorithm_node(sig_algo_node, context)
            if is_ecdsa:
                return True, hash_name

        if self._is_ec_receiver(receiver, "EllipticCurvePrivateKey", context):
            return True, None

        return False, None

    def _check_ecdsa_verify_args(
        self,
        call_node: ast.Call,
        receiver: ast.AST,
        context: AnalysisContext,
    ) -> tuple[bool, str | None]:
        """
        Check if verify call has ec.ECDSA argument: verify(signature, data, ec.ECDSA(hash)).
        """
        sig_algo_node = self._get_arg_or_keyword(call_node, 2, "signature_algorithm")
        if sig_algo_node is not None:
            is_ecdsa, hash_name = self._inspect_ecdsa_algorithm_node(sig_algo_node, context)
            if is_ecdsa:
                return True, hash_name

        if self._is_ec_receiver(receiver, "EllipticCurvePublicKey", context):
            return True, None

        return False, None

    def _inspect_ecdsa_algorithm_node(
        self,
        node: ast.AST,
        context: AnalysisContext,
    ) -> tuple[bool, str | None]:
        """
        Check if node is ec.ECDSA(...) or ECDSA(...), and extract inner hash if present.
        """
        if isinstance(node, ast.Call):
            is_ecdsa = False
            if isinstance(node.func, ast.Attribute) and node.func.attr == "ECDSA":
                is_ecdsa = True
            elif isinstance(node.func, ast.Name) and node.func.id == "ECDSA":
                is_ecdsa = True

            if is_ecdsa:
                hash_name = None
                if node.args:
                    hash_name = self._extract_hash_name(node.args[0])
                return True, hash_name

        elif isinstance(node, ast.Attribute) and node.attr == "ECDSA":
            return True, None
        elif isinstance(node, ast.Name):
            if node.id == "ECDSA":
                return True, None
            if node.id in context.symbol_table:
                sym_val = context.symbol_table[node.id]
                if isinstance(sym_val, ast.AST):
                    return self._inspect_ecdsa_algorithm_node(sym_val, context)

        return False, None

    def _extract_hash_name(self, node: ast.AST) -> str | None:
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Attribute):
                return node.func.attr
            elif isinstance(node.func, ast.Name):
                return node.func.id
        elif isinstance(node, ast.Attribute):
            return node.attr
        elif isinstance(node, ast.Name):
            return node.id
        return None

    def _is_ec_receiver(
        self,
        receiver: ast.AST,
        expected_type: str,
        context: AnalysisContext,
    ) -> bool:
        if isinstance(receiver, ast.Name):
            if receiver.id == expected_type or receiver.id in KNOWN_EC_RECEIVERS:
                return True
            if receiver.id in context.symbol_table:
                origin = context.symbol_table[receiver.id]
                if isinstance(origin, ast.Call):
                    if isinstance(origin.func, ast.Attribute) and origin.func.attr == "generate_private_key":
                        return self._is_ec_module(origin.func.value, context)
                elif isinstance(origin, ast.Name) and origin.id == expected_type:
                    return True
                elif isinstance(origin, ast.Attribute) and origin.attr == expected_type:
                    return True
        elif isinstance(receiver, ast.Attribute):
            if receiver.attr == expected_type or receiver.attr in KNOWN_EC_RECEIVERS:
                return True
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
            # Require specific EC module path — do not match broad 'cryptography'
            if "asymmetric.ec" in imported or imported.endswith(".ec"):
                return True
        elif isinstance(node, ast.Attribute) and node.attr == "ec":
            return True
        return False

    def _get_arg_or_keyword(self, call_node: ast.Call, index: int, keyword_name: str) -> ast.AST | None:
        if len(call_node.args) > index:
            return call_node.args[index]
        for kw in call_node.keywords:
            if kw.arg == keyword_name:
                return kw.value
        return None

    def _extract_keygen_metadata(self, call_node: ast.Call) -> dict[str, Any]:
        metadata: dict[str, Any] = {}
        if call_node.args:
            first_arg = call_node.args[0]
            if isinstance(first_arg, ast.Call):
                if isinstance(first_arg.func, ast.Attribute):
                    metadata["curve"] = first_arg.func.attr
                elif isinstance(first_arg.func, ast.Name):
                    metadata["curve"] = first_arg.func.id
            elif isinstance(first_arg, ast.Attribute):
                metadata["curve"] = first_arg.attr
            elif isinstance(first_arg, ast.Name):
                metadata["curve"] = first_arg.id
        return metadata

    def _create_match(
        self,
        call_node: ast.Call,
        context: AnalysisContext,
        api: str,
        operation: str,
        metadata: dict[str, Any],
    ) -> RuleMatch:
        start_line = getattr(call_node, "lineno", 1)
        end_line = getattr(call_node, "end_lineno", start_line)
        col_offset = getattr(call_node, "col_offset", 0)
        end_col_offset = getattr(call_node, "end_col_offset", None)

        observation = RawObservation(
            algorithm="ECDSA",
            library="cryptography",
            api=api,
            operation=operation,
            primitive="ASYMMETRIC",
            metadata=metadata,
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
