"""Value objects for the bounded impact graph.

The vocabularies mirror ``app.db.models.enums.ImpactNodeType`` and
``ImpactRelationship`` by value. They are restated here because the engine
never imports the database layer; the persistence layer maps between them.
"""

from dataclasses import dataclass, field
from enum import StrEnum

from app.engine.rules import MatchConfidence


class ImpactNodeType(StrEnum):
    """Kind of program element a finding touches."""

    ALGORITHM = "ALGORITHM"
    API = "API"
    FUNCTION = "FUNCTION"
    CLASS = "CLASS"
    MODULE = "MODULE"
    FILE = "FILE"


class ImpactRelationship(StrEnum):
    """How one node relates to another."""

    USES = "USES"
    CALLS = "CALLS"
    DEFINED_IN = "DEFINED_IN"
    CONTAINS = "CONTAINS"
    IMPORTS = "IMPORTS"


class ImpactScope(StrEnum):
    """How far the reported reachability was actually established.

    STATICALLY_OBSERVED is the only scope this engine produces: the graph
    describes what the parsed file shows around the match, never a
    whole-program reachability claim.
    """

    STATICALLY_OBSERVED = "STATICALLY_OBSERVED"
    SCANNED_REPOSITORY = "SCANNED_REPOSITORY"


@dataclass(frozen=True)
class ImpactNode:
    """One program element inside a finding's bounded impact.

    ``id`` is derived from the node's type and label, so the same match always
    produces the same identifiers. No random value takes part.
    """

    id: str
    node_type: ImpactNodeType
    label: str
    relationship: ImpactRelationship | None
    confidence: MatchConfidence


@dataclass(frozen=True)
class ImpactEdge:
    """A directed relationship between two nodes of one graph."""

    source_id: str
    target_id: str
    relationship: ImpactRelationship
    confidence: MatchConfidence


@dataclass(frozen=True)
class ImpactResult:
    """The bounded impact of one finding."""

    scope: ImpactScope
    confidence: MatchConfidence
    nodes: tuple[ImpactNode, ...] = ()
    relationships: tuple[ImpactEdge, ...] = ()

    @property
    def node_count(self) -> int:
        return len(self.nodes)

    def nodes_of(self, node_type: ImpactNodeType) -> tuple[ImpactNode, ...]:
        """Return the nodes of one kind, in insertion order."""
        return tuple(node for node in self.nodes if node.node_type is node_type)


@dataclass
class ImpactGraph:
    """A small insertion-ordered graph builder.

    Nodes and edges are deduplicated by identity, so a repeated relationship
    cannot inflate the blast radius.
    """

    _nodes: dict[str, ImpactNode] = field(default_factory=dict)
    _edges: dict[tuple[str, str, str], ImpactEdge] = field(default_factory=dict)

    def add_node(self, node: ImpactNode) -> str:
        """Add a node if it is new and return its identifier."""
        self._nodes.setdefault(node.id, node)
        return node.id

    def add_edge(
        self,
        source_id: str,
        target_id: str,
        relationship: ImpactRelationship,
        confidence: MatchConfidence,
    ) -> None:
        """Add a directed relationship between two nodes already in the graph."""
        if source_id not in self._nodes or target_id not in self._nodes:
            raise KeyError("both endpoints must be in the graph")
        key = (source_id, target_id, relationship.value)
        self._edges.setdefault(
            key,
            ImpactEdge(
                source_id=source_id,
                target_id=target_id,
                relationship=relationship,
                confidence=confidence,
            ),
        )

    def to_result(self, scope: ImpactScope, confidence: MatchConfidence) -> ImpactResult:
        """Freeze the graph into a result."""
        return ImpactResult(
            scope=scope,
            confidence=confidence,
            nodes=tuple(self._nodes.values()),
            relationships=tuple(self._edges.values()),
        )
