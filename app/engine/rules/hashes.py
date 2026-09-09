from __future__ import annotations

import ast
from typing import Any

from app.engine.models import AnalysisContext, RawObservation, RuleMatch
from app.engine.rules.base import CryptoRule

# Normalization map for hash algorithms
HASH_ALGORITHMS_CRYPTOGRAPHY = {
    "MD5": "MD5",
    "SHA1": "SHA-1",
    "SHA224": "SHA-224",
    "SHA256": "SHA-256",
    "SHA384": "SHA-384",
    "SHA512": "SHA-512",
    "SHA512_224": "SHA-512/224",
    "SHA512_256": "SHA-512/256",
    "SHA3_224": "SHA3-224",
    "SHA3_256": "SHA3-256",
    "SHA3_384": "SHA3-384",
    "SHA3_512": "SHA3-512",
    "SHAKE128": "SHAKE128",
    "SHAKE256": "SHAKE256",
    "BLAKE2b": "BLAKE2b",
    "BLAKE2s": "BLAKE2s",
}

HASH_ALGORITHMS_HASHLIB = {
    "md5": "MD5",
    "sha1": "SHA-1",
    "sha224": "SHA-224",
    "sha256": "SHA-256",
    "sha384": "SHA-384",
    "sha512": "SHA-512",
    "sha3_224": "SHA3-224",
    "sha3_256": "SHA3-256",
    "sha3_384": "SHA3-384",
    "sha3_512": "SHA3-512",
    "shake_128": "SHAKE128",
    "shake_256": "SHAKE256",
    "blake2b": "BLAKE2b",
    "blake2s": "BLAKE2s",
}


class HashRule(CryptoRule):
    """
    Deterministic AST rule detecting hash function invocations across MD5, SHA-1, SHA-2, SHA-3, and BLAKE.
    Inspects Call nodes targeting cryptography.hazmat.primitives.hashes and standard library hashlib.
    Strictly records observations; does not make vulnerability judgments.
    """

    rule_id: str = "PY-CRYPTO-HASH"

    def evaluate(
        self,
        node: ast.AST,
        context: AnalysisContext,
    ) -> RuleMatch | None:
        if not isinstance(node, ast.Call):
            return None

        # Case 1: Method or module attribute call (hashes.SHA256(), hashlib.sha256(), hashlib.new("sha256"))
        if isinstance(node.func, ast.Attribute):
            return self._evaluate_attribute_call(node, node.func, context)

        # Case 2: Directly imported function/class call (SHA256(), sha256())
        elif isinstance(node.func, ast.Name):
            return self._evaluate_name_call(node, node.func, context)

        return None

    def _evaluate_attribute_call(
        self,
        call_node: ast.Call,
        func_node: ast.Attribute,
        context: AnalysisContext,
    ) -> RuleMatch | None:
        attr_name = func_node.attr
        receiver = func_node.value

        # 1. cryptography: hashes.SHA256()
        if attr_name in HASH_ALGORITHMS_CRYPTOGRAPHY:
            if self._is_cryptography_hashes_module(receiver, context):
                canonical_algo = HASH_ALGORITHMS_CRYPTOGRAPHY[attr_name]
                return self._create_match(
                    call_node=call_node,
                    context=context,
                    algorithm=canonical_algo,
                    library="cryptography",
                    api=f"hashes.{attr_name}",
                )

        # 2. hashlib: hashlib.sha256()
        if attr_name in HASH_ALGORITHMS_HASHLIB:
            if self._is_hashlib_module(receiver, context):
                canonical_algo = HASH_ALGORITHMS_HASHLIB[attr_name]
                return self._create_match(
                    call_node=call_node,
                    context=context,
                    algorithm=canonical_algo,
                    library="hashlib",
                    api=f"hashlib.{attr_name}",
                )

        # 3. hashlib.new("sha256")
        if attr_name == "new" and self._is_hashlib_module(receiver, context):
            algo_name = self._extract_hashlib_new_algo(call_node)
            if algo_name:
                return self._create_match(
                    call_node=call_node,
                    context=context,
                    algorithm=algo_name,
                    library="hashlib",
                    api="hashlib.new",
                )

        return None

    def _evaluate_name_call(
        self,
        call_node: ast.Call,
        func_node: ast.Name,
        context: AnalysisContext,
    ) -> RuleMatch | None:
        name = func_node.id

        # Direct cryptography hash import: from cryptography.hazmat.primitives.hashes import SHA256
        if name in HASH_ALGORITHMS_CRYPTOGRAPHY:
            imported = context.imports.get(name, "")
            if "hashes" in imported or "cryptography" in imported:
                canonical_algo = HASH_ALGORITHMS_CRYPTOGRAPHY[name]
                return self._create_match(
                    call_node=call_node,
                    context=context,
                    algorithm=canonical_algo,
                    library="cryptography",
                    api=f"hashes.{name}",
                )

        # Direct hashlib hash import: from hashlib import sha256
        if name in HASH_ALGORITHMS_HASHLIB:
            imported = context.imports.get(name, "")
            if "hashlib" in imported:
                canonical_algo = HASH_ALGORITHMS_HASHLIB[name]
                return self._create_match(
                    call_node=call_node,
                    context=context,
                    algorithm=canonical_algo,
                    library="hashlib",
                    api=f"hashlib.{name}",
                )

        return None

    def _is_cryptography_hashes_module(self, node: ast.AST, context: AnalysisContext) -> bool:
        if isinstance(node, ast.Name):
            if node.id == "hashes":
                return True
            imported = context.imports.get(node.id, "")
            if "hashes" in imported or "cryptography" in imported:
                return True
        elif isinstance(node, ast.Attribute) and node.attr == "hashes":
            return True
        return False

    def _is_hashlib_module(self, node: ast.AST, context: AnalysisContext) -> bool:
        if isinstance(node, ast.Name):
            if node.id == "hashlib":
                return True
            imported = context.imports.get(node.id, "")
            if "hashlib" in imported:
                return True
        elif isinstance(node, ast.Attribute) and node.attr == "hashlib":
            return True
        return False

    def _extract_hashlib_new_algo(self, call_node: ast.Call) -> str | None:
        """
        Extract algorithm string from hashlib.new("sha256").
        """
        if call_node.args:
            first = call_node.args[0]
            if isinstance(first, ast.Constant) and isinstance(first.value, str):
                raw = first.value.lower()
                return HASH_ALGORITHMS_HASHLIB.get(raw, first.value.upper())
        for kw in call_node.keywords:
            if kw.arg == "name" and isinstance(kw.value, ast.Constant) and isinstance(kw.value.value, str):
                raw = kw.value.value.lower()
                return HASH_ALGORITHMS_HASHLIB.get(raw, kw.value.value.upper())
        return None

    def _create_match(
        self,
        call_node: ast.Call,
        context: AnalysisContext,
        algorithm: str,
        library: str,
        api: str,
    ) -> RuleMatch:
        start_line = getattr(call_node, "lineno", 1)
        end_line = getattr(call_node, "end_lineno", start_line)
        col_offset = getattr(call_node, "col_offset", 0)
        end_col_offset = getattr(call_node, "end_col_offset", None)

        observation = RawObservation(
            algorithm=algorithm,
            library=library,
            api=api,
            operation="HASH",
            primitive="HASH",
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
