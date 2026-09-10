"""Bounded static impact analysis.

The graph describes only what the parse already established around a match:
the algorithm, the API called, the function and class the call sits in, the
module, and the file. Nothing is inferred beyond that, and no caller outside
the file is claimed, so the result is a blast radius that can be checked
against the source line by line.
"""

from app.engine.impact.models import (
    ImpactGraph,
    ImpactNode,
    ImpactNodeType,
    ImpactRelationship,
    ImpactResult,
    ImpactScope,
)
from app.engine.rules import RuleMatch


def _node_id(node_type: ImpactNodeType, label: str) -> str:
    """Return an identifier derived only from the node itself.

    Identifiers are local to one finding's graph and contain no random value,
    so the same match always yields the same graph.
    """
    return f"{node_type.value}:{label}"


def analyze(match: RuleMatch, module_path: str | None = None) -> ImpactResult:
    """Return the bounded impact of one rule match.

    The chain is built outwards from the algorithm and stops at the first
    element the match does not establish. A missing enclosing class is simply
    absent from the graph; it is never invented.
    """
    confidence = match.confidence
    graph = ImpactGraph()

    algorithm_id = graph.add_node(
        ImpactNode(
            id=_node_id(ImpactNodeType.ALGORITHM, match.algorithm),
            node_type=ImpactNodeType.ALGORITHM,
            label=match.algorithm,
            relationship=None,
            confidence=confidence,
        )
    )

    innermost = algorithm_id
    if match.api:
        innermost = _link(
            graph,
            ImpactNodeType.API,
            match.api,
            innermost,
            ImpactRelationship.USES,
            confidence,
        )

    if match.enclosing_function:
        innermost = _link(
            graph,
            ImpactNodeType.FUNCTION,
            match.enclosing_function,
            innermost,
            ImpactRelationship.CALLS,
            confidence,
        )

    if match.enclosing_class:
        innermost = _link(
            graph,
            ImpactNodeType.CLASS,
            match.enclosing_class,
            innermost,
            ImpactRelationship.CONTAINS,
            confidence,
        )

    if module_path:
        innermost = _link(
            graph,
            ImpactNodeType.MODULE,
            module_path,
            innermost,
            ImpactRelationship.CONTAINS,
            confidence,
        )

    if match.file_path:
        file_id = graph.add_node(
            ImpactNode(
                id=_node_id(ImpactNodeType.FILE, match.file_path),
                node_type=ImpactNodeType.FILE,
                label=match.file_path,
                relationship=ImpactRelationship.DEFINED_IN,
                confidence=confidence,
            )
        )
        # The innermost element is defined in the file, so the edge points
        # from the element outwards rather than the other way round.
        graph.add_edge(innermost, file_id, ImpactRelationship.DEFINED_IN, confidence)

    return graph.to_result(scope=ImpactScope.STATICALLY_OBSERVED, confidence=confidence)


def _link(
    graph: ImpactGraph,
    node_type: ImpactNodeType,
    label: str,
    target_id: str,
    relationship: ImpactRelationship,
    confidence,
) -> str:
    """Add a node and point it at the element it contains or calls."""
    node_id = graph.add_node(
        ImpactNode(
            id=_node_id(node_type, label),
            node_type=node_type,
            label=label,
            relationship=relationship,
            confidence=confidence,
        )
    )
    graph.add_edge(node_id, target_id, relationship, confidence)
    return node_id
