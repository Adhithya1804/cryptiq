from __future__ import annotations

import ast
from typing import Any

from app.engine.models import AnalysisContext, RawObservation, RuleMatch
from app.engine.rules.base import CryptoRule

RSA_SIGNATURE_PADDINGS = {"PSS", "PKCS1v15"}
RSA_ENCRYPTION_PADDINGS = {"OAEP", "PKCS1v15"}
RSA_ALL_PADDINGS = RSA_SIGNATURE_PADDINGS | RSA_ENCRYPTION_PADDINGS

KNOWN_RSA_RECEIVERS = {
    "RSAPrivateKey",
    "RSAPublicKey",
    "rsa_private_key",
    "rsa_public_key",
    "rsa_key",
}


class RSARule(CryptoRule):
    """
    Deterministic AST rule detecting explicit RSA cryptographic semantics.
    Inspects Call and Attribute nodes for cryptography library RSA APIs
    (e.g., RSAPrivateKey.sign, RSAPublicKey.verify, rsa.generate_private_key).
    """

    rule_id: str = "PY-CRYPTO-RSA"

    def evaluate(
        self,
        node: ast.AST,
        context: AnalysisContext,
    ) -> RuleMatch | None:
        """
        Pure evaluation of an AST node.
        Returns a RuleMatch if explicit RSA semantics are detected, else None.
        """
        if not isinstance(node, ast.Call):
            return None

        # Case 1: Method call on an object (e.g., private_key.sign(...), rsa.generate_private_key(...))
        if isinstance(node.func, ast.Attribute):
            match = self._evaluate_attribute_call(node, node.func, context)
            if match is not None:
                return match

        # Case 2: Directly imported function call (e.g., generate_private_key(...))
        elif isinstance(node.func, ast.Name):
            match = self._evaluate_name_call(node, node.func, context)
            if match is not None:
                return match

        return None

    def _evaluate_attribute_call(
        self,
        call_node: ast.Call,
        func_node: ast.Attribute,
        context: AnalysisContext,
    ) -> RuleMatch | None:
        method_name = func_node.attr
        receiver = func_node.value

        # --- 1. RSA Key Generation: rsa.generate_private_key(...) ---
        if method_name == "generate_private_key":
            if self._is_rsa_module(receiver, context):
                metadata = self._extract_keygen_metadata(call_node)
                return self._create_match(
                    call_node=call_node,
                    context=context,
                    api="rsa.generate_private_key",
                    operation="KEYGEN",
                    metadata=metadata,
                )

        # --- 2. RSA Digital Signature: private_key.sign(...) ---
        elif method_name == "sign":
            is_rsa, padding_name = self._check_rsa_signature_semantics(call_node, receiver, context)
            if is_rsa:
                metadata = {}
                if padding_name:
                    metadata["padding"] = padding_name
                hash_algo = self._extract_hash_arg(call_node, arg_index=2)
                if hash_algo:
                    metadata["hash_algorithm"] = hash_algo

                return self._create_match(
                    call_node=call_node,
                    context=context,
                    api="RSAPrivateKey.sign",
                    operation="SIGN",
                    metadata=metadata,
                )

        # --- 3. RSA Signature Verification: public_key.verify(...) ---
        elif method_name == "verify":
            is_rsa, padding_name = self._check_rsa_verify_semantics(call_node, receiver, context)
            if is_rsa:
                metadata = {}
                if padding_name:
                    metadata["padding"] = padding_name
                hash_algo = self._extract_hash_arg(call_node, arg_index=3)
                if hash_algo:
                    metadata["hash_algorithm"] = hash_algo

                return self._create_match(
                    call_node=call_node,
                    context=context,
                    api="RSAPublicKey.verify",
                    operation="VERIFY",
                    metadata=metadata,
                )

        # --- 4. RSA Decryption: private_key.decrypt(...) ---
        elif method_name == "decrypt":
            is_rsa, padding_name = self._check_rsa_encryption_semantics(call_node, receiver, context)
            if is_rsa:
                metadata = {}
                if padding_name:
                    metadata["padding"] = padding_name

                return self._create_match(
                    call_node=call_node,
                    context=context,
                    api="RSAPrivateKey.decrypt",
                    operation="DECRYPT",
                    metadata=metadata,
                )

        # --- 5. RSA Encryption: public_key.encrypt(...) ---
        elif method_name == "encrypt":
            is_rsa, padding_name = self._check_rsa_encryption_semantics(call_node, receiver, context)
            if is_rsa:
                metadata = {}
                if padding_name:
                    metadata["padding"] = padding_name

                return self._create_match(
                    call_node=call_node,
                    context=context,
                    api="RSAPublicKey.encrypt",
                    operation="ENCRYPT",
                    metadata=metadata,
                )

        return None

    def _evaluate_name_call(
        self,
        call_node: ast.Call,
        func_node: ast.Name,
        context: AnalysisContext,
    ) -> RuleMatch | None:
        # e.g., generate_private_key(...) directly imported
        if func_node.id == "generate_private_key":
            imported_from = context.imports.get("generate_private_key", "")
            if "asymmetric.rsa" in imported_from or imported_from.endswith(".rsa"):
                metadata = self._extract_keygen_metadata(call_node)
                return self._create_match(
                    call_node=call_node,
                    context=context,
                    api="rsa.generate_private_key",
                    operation="KEYGEN",
                    metadata=metadata,
                )
        return None

    def _check_rsa_signature_semantics(
        self,
        call_node: ast.Call,
        receiver: ast.AST,
        context: AnalysisContext,
    ) -> tuple[bool, str | None]:
        """
        Check if a .sign() call corresponds to RSA semantics.
        In cryptography library:
        - RSA: sign(data, padding, algorithm) where padding is PSS or PKCS1v15
        - ECDSA: sign(data, signature_algorithm) where signature_algorithm is ec.ECDSA(...)
        - Ed25519: sign(data)
        """
        # 1. Check padding argument (positional arg 1 or keyword 'padding')
        padding_node = self._get_arg_or_keyword(call_node, 1, "padding")
        if padding_node is not None:
            is_padding, padding_name = self._inspect_padding_node(padding_node, RSA_SIGNATURE_PADDINGS, context)
            if is_padding:
                return True, padding_name

        # 2. Check receiver object identity or symbol table
        if self._is_rsa_receiver(receiver, "RSAPrivateKey", context):
            return True, None

        return False, None

    def _check_rsa_verify_semantics(
        self,
        call_node: ast.Call,
        receiver: ast.AST,
        context: AnalysisContext,
    ) -> tuple[bool, str | None]:
        """
        Check if a .verify() call corresponds to RSA semantics.
        In cryptography library:
        - RSA: verify(signature, data, padding, algorithm)
        """
        padding_node = self._get_arg_or_keyword(call_node, 2, "padding")
        if padding_node is not None:
            is_padding, padding_name = self._inspect_padding_node(padding_node, RSA_SIGNATURE_PADDINGS, context)
            if is_padding:
                return True, padding_name

        if self._is_rsa_receiver(receiver, "RSAPublicKey", context):
            return True, None

        return False, None

    def _check_rsa_encryption_semantics(
        self,
        call_node: ast.Call,
        receiver: ast.AST,
        context: AnalysisContext,
    ) -> tuple[bool, str | None]:
        """
        Check if an .encrypt() or .decrypt() call corresponds to RSA asymmetric encryption.
        """
        padding_node = self._get_arg_or_keyword(call_node, 1, "padding")
        if padding_node is not None:
            is_padding, padding_name = self._inspect_padding_node(padding_node, RSA_ENCRYPTION_PADDINGS, context)
            if is_padding:
                return True, padding_name

        if self._is_rsa_receiver(receiver, "RSAPrivateKey", context) or self._is_rsa_receiver(receiver, "RSAPublicKey", context):
            return True, None

        return False, None

    def _inspect_padding_node(
        self,
        node: ast.AST,
        allowed_paddings: set[str],
        context: AnalysisContext,
    ) -> tuple[bool, str | None]:
        """
        Inspect an AST node passed as a padding parameter to determine if it is an RSA padding.
        """
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Attribute) and node.func.attr in allowed_paddings:
                return True, node.func.attr
            elif isinstance(node.func, ast.Name) and node.func.id in allowed_paddings:
                return True, node.func.id
        elif isinstance(node, ast.Attribute) and node.attr in allowed_paddings:
            return True, node.attr
        elif isinstance(node, ast.Name):
            if node.id in allowed_paddings:
                return True, node.id
            # Check symbol table if padding was instantiated earlier
            if node.id in context.symbol_table:
                sym_val = context.symbol_table[node.id]
                if isinstance(sym_val, ast.AST):
                    return self._inspect_padding_node(sym_val, allowed_paddings, context)

        return False, None

    def _is_rsa_receiver(
        self,
        receiver: ast.AST,
        expected_type: str,
        context: AnalysisContext,
    ) -> bool:
        """
        Determine whether a call receiver AST node resolves to an RSA key.
        """
        if isinstance(receiver, ast.Name):
            if receiver.id == expected_type or receiver.id in KNOWN_RSA_RECEIVERS:
                return True
            # Check symbol table for tracked variable origin or type annotation
            if receiver.id in context.symbol_table:
                origin = context.symbol_table[receiver.id]
                if isinstance(origin, ast.Call):
                    if isinstance(origin.func, ast.Attribute) and origin.func.attr == "generate_private_key":
                        return self._is_rsa_module(origin.func.value, context)
                elif isinstance(origin, ast.Name) and origin.id == expected_type:
                    return True
                elif isinstance(origin, ast.Attribute) and origin.attr == expected_type:
                    return True
        elif isinstance(receiver, ast.Attribute):
            if receiver.attr == expected_type or receiver.attr in KNOWN_RSA_RECEIVERS:
                return True

        return False

    def _is_rsa_module(self, node: ast.AST, context: AnalysisContext) -> bool:
        """
        Check if an AST node refers specifically to the rsa module.
        Must NOT match other cryptography submodules (ec, ed25519, x25519).
        """
        if isinstance(node, ast.Name):
            if node.id == "rsa":
                return True
            imported = context.imports.get(node.id, "")
            # Require specific RSA module path — do not match broad 'cryptography'
            if "asymmetric.rsa" in imported or imported.endswith(".rsa"):
                return True
        elif isinstance(node, ast.Attribute):
            if node.attr == "rsa":
                return True
        return False

    def _get_arg_or_keyword(self, call_node: ast.Call, index: int, keyword_name: str) -> ast.AST | None:
        """
        Retrieve an argument by positional index or keyword argument name.
        """
        if len(call_node.args) > index:
            return call_node.args[index]
        for kw in call_node.keywords:
            if kw.arg == keyword_name:
                return kw.value
        return None

    def _extract_hash_arg(self, call_node: ast.Call, arg_index: int) -> str | None:
        """
        Extract the hash algorithm name if passed as an argument.
        """
        arg_node = self._get_arg_or_keyword(call_node, arg_index, "algorithm")
        if arg_node is None:
            return None

        if isinstance(arg_node, ast.Call):
            if isinstance(arg_node.func, ast.Attribute):
                return arg_node.func.attr
            elif isinstance(arg_node.func, ast.Name):
                return arg_node.func.id
        elif isinstance(arg_node, ast.Attribute):
            return arg_node.attr
        elif isinstance(arg_node, ast.Name):
            return arg_node.id
        return None

    def _extract_keygen_metadata(self, call_node: ast.Call) -> dict[str, Any]:
        """
        Extract key_size and public_exponent from rsa.generate_private_key call.
        """
        metadata: dict[str, Any] = {}
        for kw in call_node.keywords:
            if kw.arg == "key_size" and isinstance(kw.value, ast.Constant):
                metadata["key_size"] = kw.value.value
            elif kw.arg == "public_exponent" and isinstance(kw.value, ast.Constant):
                metadata["public_exponent"] = kw.value.value
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
            algorithm="RSA",
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
