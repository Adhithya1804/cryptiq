"""Lightweight, deterministic in-memory impact graph for Cryptiq."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Set, Tuple

from cryptiq.core.enums import ConfidenceLevel, ImpactRelationship, ImpactScope
from cryptiq.impact.models import ImpactEdge, ImpactNode, ImpactResult


class ImpactGraph:
    """Represents a bounded, verifiable relationship graph for a cryptographic finding."""

    def __init__(self, finding_id: str = ""):
        self.finding_id = finding_id
        self._nodes: Dict[str, ImpactNode] = {}
        self._edges: List[ImpactEdge] = []
        self._adj: Dict[str, List[str]] = {}
        self._edge_keys: Set[Tuple[str, str, str]] = set()

    def add_node(self, node: ImpactNode) -> None:
        """Add a node to the graph if not already present."""
        if node.id not in self._nodes:
            self._nodes[node.id] = node
            if node.id not in self._adj:
                self._adj[node.id] = []

    def add_relationship(
        self,
        edge_or_source: Optional[ImpactEdge | str] = None,
        target_id: Optional[str] = None,
        relationship: Optional[ImpactRelationship] = None,
        confidence: ConfidenceLevel = ConfidenceLevel.CONFIRMED,
        *,
        source_id: Optional[str] = None,
    ) -> None:
        """Add a directed relationship between two nodes."""
        if isinstance(edge_or_source, ImpactEdge):
            edge = edge_or_source
        else:
            src = source_id or edge_or_source
            if src is None or target_id is None or relationship is None:
                raise ValueError("source_id, target_id, and relationship are required")
            edge = ImpactEdge(
                source_id=src,
                target_id=target_id,
                relationship=relationship,
                confidence=confidence,
            )

        key = (edge.source_id, edge.target_id, edge.relationship.value)
        if key not in self._edge_keys:
            self._edge_keys.add(key)
            self._edges.append(edge)
            self._adj.setdefault(edge.source_id, []).append(edge.target_id)

    def nodes(self) -> List[ImpactNode]:
        """Return all nodes in insertion order."""
        return list(self._nodes.values())

    def relationships(self) -> List[ImpactEdge]:
        """Return all directed relationships in insertion order."""
        return list(self._edges)

    def get_node(self, node_id: str) -> Optional[ImpactNode]:
        """Retrieve a node by its unique identifier."""
        return self._nodes.get(node_id)

    def has_node(self, node_id: str) -> bool:
        """Check if a node exists in the graph."""
        return node_id in self._nodes

    def neighbors(self, node_id: str) -> List[ImpactNode]:
        """Return all destination nodes connected from the given node."""
        target_ids = self._adj.get(node_id, [])
        return [self._nodes[tid] for tid in target_ids if tid in self._nodes]

    def edges_from(self, node_id: str) -> List[ImpactEdge]:
        """Return all edges originating at the given node."""
        return [e for e in self._edges if e.source_id == node_id]

    def to_result(
        self,
        scope: ImpactScope = ImpactScope.STATICALLY_OBSERVED,
        confidence: ConfidenceLevel = ConfidenceLevel.CONFIRMED,
    ) -> ImpactResult:
        """Convert the in-memory graph into an immutable ImpactResult."""
        return ImpactResult(
            scope=scope,
            nodes=self.nodes(),
            relationships=self.relationships(),
            confidence=confidence,
        )

    def to_dict(self) -> Dict[str, Any]:
        """Serialize the graph to a JSON-compatible dictionary."""
        return {
            "finding_id": self.finding_id,
            "nodes": [n.to_dict() for n in self.nodes()],
            "relationships": [e.to_dict() for e in self.relationships()],
        }
