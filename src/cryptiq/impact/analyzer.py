"""Deterministic bounded static impact analyzer for Cryptiq."""

from __future__ import annotations

from typing import Any, Dict, Optional, Union

from cryptiq.core.enums import (
    ConfidenceLevel,
    ImpactNodeType,
    ImpactRelationship,
    ImpactScope,
)
from cryptiq.impact.graph import ImpactGraph
from cryptiq.impact.models import ImpactEdge, ImpactNode, ImpactResult


def _extract_val(obj: Any, key: str, default: Any = None) -> Any:
    """Safely extract attribute or dictionary key."""
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


class ImpactAnalyzer:
    """Constructs a bounded static impact graph strictly from parsed evidence."""

    def analyze(
        self,
        raw_finding: Any,
        parsed_context: Optional[Any] = None,
    ) -> ImpactResult:
        """Analyze source context and construct a bounded, verifiable impact result.

        Follows strict evidence hierarchy:
        1. Exact Cryptographic API
        2. Call-site / function containing call
        3. Class containing function (only if statically proven; never fabricated)
        4. Module / File containing the definition
        """
        # Extract finding identity and cryptographic details
        finding_id = str(_extract_val(raw_finding, "id", "") or _extract_val(raw_finding, "finding_id", "f-0"))
        algorithm = _extract_val(raw_finding, "algorithm", "") or "UNKNOWN_ALGORITHM"
        api = _extract_val(raw_finding, "api", "") or _extract_val(raw_finding, "api_or_symbol", "")

        # Extract context fields defensively
        ctx = parsed_context if parsed_context is not None else _extract_val(raw_finding, "evidence", None)
        file_path = (
            _extract_val(ctx, "file_path", None)
            or _extract_val(ctx, "file", None)
            or _extract_val(raw_finding, "file_path", None)
            or _extract_val(raw_finding, "file", None)
        )
        function_name = _extract_val(ctx, "function_name", None) or _extract_val(ctx, "function", None)
        class_name = _extract_val(ctx, "class_name", None) or _extract_val(ctx, "class", None)
        module_name = _extract_val(ctx, "module_name", None) or _extract_val(ctx, "module", None)
        raw_confidence = (
            _extract_val(raw_finding, "confidence", None)
            or _extract_val(ctx, "confidence", None)
            or ConfidenceLevel.CONFIRMED
        )

        if isinstance(raw_confidence, str):
            try:
                confidence = ConfidenceLevel(raw_confidence)
            except ValueError:
                confidence = ConfidenceLevel.CONFIRMED
        elif isinstance(raw_confidence, ConfidenceLevel):
            confidence = raw_confidence
        else:
            confidence = ConfidenceLevel.CONFIRMED

        # Scope defaults strictly to STATICALLY_OBSERVED unless broader scope established
        requested_scope = _extract_val(ctx, "scope", None)
        if isinstance(requested_scope, ImpactScope):
            scope = requested_scope
        elif requested_scope == ImpactScope.SCANNED_REPOSITORY.value:
            scope = ImpactScope.SCANNED_REPOSITORY
        else:
            scope = ImpactScope.STATICALLY_OBSERVED

        graph = ImpactGraph(finding_id=finding_id)

        # 1. Algorithm Node
        algo_node_id = f"{finding_id}:algo:{algorithm}"
        algo_node = ImpactNode(
            id=algo_node_id,
            finding_id=finding_id,
            node_type=ImpactNodeType.ALGORITHM,
            label=algorithm,
            confidence=confidence,
        )
        graph.add_node(algo_node)

        prev_node_id = algo_node_id

        # 2. API Node (if known)
        api_node_id = None
        if api:
            api_node_id = f"{finding_id}:api:{api}"
            api_node = ImpactNode(
                id=api_node_id,
                finding_id=finding_id,
                node_type=ImpactNodeType.API,
                label=api,
                relationship=ImpactRelationship.USES,
                confidence=confidence,
            )
            graph.add_node(api_node)
            graph.add_relationship(
                source_id=api_node_id,
                target_id=algo_node_id,
                relationship=ImpactRelationship.USES,
                confidence=confidence,
            )
            prev_node_id = api_node_id

        # 3. Function Node (if statically present)
        func_node_id = None
        if function_name and function_name.strip() and function_name != "<module>":
            clean_func = function_name.strip()
            func_label = clean_func if clean_func.endswith("()") else f"{clean_func}()"
            func_node_id = f"{finding_id}:func:{clean_func}"
            func_node = ImpactNode(
                id=func_node_id,
                finding_id=finding_id,
                node_type=ImpactNodeType.FUNCTION,
                label=func_label,
                relationship=ImpactRelationship.CALLS if api_node_id else ImpactRelationship.USES,
                confidence=confidence,
            )
            graph.add_node(func_node)
            graph.add_relationship(
                source_id=func_node_id,
                target_id=prev_node_id,
                relationship=ImpactRelationship.CALLS if api_node_id else ImpactRelationship.USES,
                confidence=confidence,
            )
            prev_node_id = func_node_id

        # 4. Class Node (ONLY if statically established; do NOT invent a class)
        class_node_id = None
        if class_name and class_name.strip():
            clean_class = class_name.strip()
            class_node_id = f"{finding_id}:class:{clean_class}"
            class_node = ImpactNode(
                id=class_node_id,
                finding_id=finding_id,
                node_type=ImpactNodeType.CLASS,
                label=clean_class,
                relationship=ImpactRelationship.CONTAINS if func_node_id else ImpactRelationship.USES,
                confidence=confidence,
            )
            graph.add_node(class_node)
            graph.add_relationship(
                source_id=class_node_id,
                target_id=prev_node_id,
                relationship=ImpactRelationship.CONTAINS if func_node_id else ImpactRelationship.USES,
                confidence=confidence,
            )
            prev_node_id = class_node_id

        # 5. File Node (if statically present)
        if file_path and file_path.strip():
            clean_file = file_path.strip()
            file_node_id = f"{finding_id}:file:{clean_file}"
            file_node = ImpactNode(
                id=file_node_id,
                finding_id=finding_id,
                node_type=ImpactNodeType.FILE,
                label=clean_file,
                relationship=ImpactRelationship.DEFINED_IN,
                confidence=confidence,
            )
            graph.add_node(file_node)
            # The innermost container is defined in file
            graph.add_relationship(
                source_id=prev_node_id,
                target_id=file_node_id,
                relationship=ImpactRelationship.DEFINED_IN,
                confidence=confidence,
            )

        return graph.to_result(scope=scope, confidence=confidence)
