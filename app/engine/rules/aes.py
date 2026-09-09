from __future__ import annotations

import ast
from typing import Any

from app.engine.models import AnalysisContext, RawObservation, RuleMatch
from app.engine.rules.base import CryptoRule


class AESRule(CryptoRule):
    """
    Deterministic AST rule detecting symmetric AES cryptographic API use.
    Inspects Call and Attribute nodes for cryptography and pyca APIs
    (e.g., algorithms.AES, Cipher(algorithms.AES(key), ...), AES.new).
    Does NOT mark AES as vulnerable; captures factual symmetric primitive usage for policy review.
    """

    rule_id: str = "PY-CRYPTO-AES"

    def evaluate(
        self,
        node: ast.AST,
        context: AnalysisContext,
    ) -> RuleMatch | None:
        if not isinstance(node, ast.Call):
            return None

        # Case 1: algorithms.AES(key) or AES.new(key, ...)
        if isinstance(node.func, ast.Attribute):
            return self._evaluate_attribute_call(node, node.func, context)

        # Case 2: AES(key) directly imported
        elif isinstance(node.func, ast.Name):
            return self._evaluate_name_call(node, node.func, context)

        return None

    def _evaluate_attribute_call(
        self,
        call_node: ast.Call,
        func_node: ast.Attribute,
        context: AnalysisContext,
    ) -> RuleMatch | None:
        # 1. algorithms.AES(key)
        if func_node.attr == "AES":
            if self._is_aes_module_or_class(func_node.value, context):
                metadata = self._extract_aes_metadata(call_node, context)
                return self._create_match(
                    call_node=call_node,
                    context=context,
                    api="algorithms.AES",
                    operation="SYMMETRIC_ENCRYPTION",
                    metadata=metadata,
                )

        # 2. AES.new(key, mode, ...)
        elif func_node.attr == "new":
            if isinstance(func_node.value, ast.Name) and func_node.value.id == "AES":
                metadata = self._extract_aes_metadata(call_node, context)
                return self._create_match(
                    call_node=call_node,
                    context=context,
                    api="AES.new",
                    operation="SYMMETRIC_ENCRYPTION",
                    metadata=metadata,
                )

        return None

    def _evaluate_name_call(
        self,
        call_node: ast.Call,
        func_node: ast.Name,
        context: AnalysisContext,
    ) -> RuleMatch | None:
        if func_node.id == "AES":
            imported = context.imports.get("AES", "")
            if "algorithms" in imported or "ciphers" in imported or "Crypto" in imported:
                metadata = self._extract_aes_metadata(call_node, context)
                return self._create_match(
                    call_node=call_node,
                    context=context,
                    api="algorithms.AES",
                    operation="SYMMETRIC_ENCRYPTION",
                    metadata=metadata,
                )
        return None

    def _is_aes_module_or_class(self, node: ast.AST, context: AnalysisContext) -> bool:
        if isinstance(node, ast.Name):
            if node.id in ("algorithms", "ciphers"):
                return True
            imported = context.imports.get(node.id, "")
            if "algorithms" in imported or "ciphers" in imported or "cryptography" in imported:
                return True
        elif isinstance(node, ast.Attribute):
            if node.attr in ("algorithms", "ciphers"):
                return True
        return False

    def _extract_aes_metadata(self, call_node: ast.Call, context: AnalysisContext) -> dict[str, Any]:
        """
        Extract key length or mode context if deterministically observable.
        """
        metadata: dict[str, Any] = {}
        # Check parent node for Cipher(algorithms.AES(key), mode)
        parent = context.parent_map.get(id(call_node))
        if isinstance(parent, ast.Call):
            # Check for mode argument in parent Cipher call
            if len(parent.args) > 1:
                mode_node = parent.args[1]
                mode_name = self._inspect_mode_node(mode_node)
                if mode_name:
                    metadata["mode"] = mode_name
        return metadata

    def _inspect_mode_node(self, node: ast.AST) -> str | None:
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
            algorithm="AES",
            library="cryptography",
            api=api,
            operation=operation,
            primitive="SYMMETRIC",
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
