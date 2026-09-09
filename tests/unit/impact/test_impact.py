"""Unit tests for Phase 9: Bounded Impact Engine."""

from __future__ import annotations

import unittest

from cryptiq.core.enums import (
    ConfidenceLevel,
    ImpactNodeType,
    ImpactRelationship,
    ImpactScope,
)
from cryptiq.impact.analyzer import ImpactAnalyzer
from cryptiq.impact.graph import ImpactGraph
from cryptiq.impact.models import ImpactNode
from tests.fixtures.sample_contexts import (
    make_ambiguous_finding,
    make_class_level_finding,
    make_function_level_finding,
    make_missing_context_finding,
)


class TestImpactGraph(unittest.TestCase):
    """Verify lightweight in-memory graph operations."""

    def test_add_node_and_relationships(self):
        graph = ImpactGraph(finding_id="f-test")
        n1 = ImpactNode(
            id="n1",
            finding_id="f-test",
            node_type=ImpactNodeType.ALGORITHM,
            label="RSA",
            confidence=ConfidenceLevel.CONFIRMED,
        )
        n2 = ImpactNode(
            id="n2",
            finding_id="f-test",
            node_type=ImpactNodeType.API,
            label="RSAPrivateKey.sign",
            confidence=ConfidenceLevel.CONFIRMED,
        )

        graph.add_node(n1)
        graph.add_node(n2)
        graph.add_relationship(
            source_id="n2",
            target_id="n1",
            relationship=ImpactRelationship.USES,
            confidence=ConfidenceLevel.CONFIRMED,
        )

        self.assertEqual(len(graph.nodes()), 2)
        self.assertEqual(len(graph.relationships()), 1)
        self.assertTrue(graph.has_node("n1"))
        self.assertTrue(graph.has_node("n2"))

        neighbors = graph.neighbors("n2")
        self.assertEqual(len(neighbors), 1)
        self.assertEqual(neighbors[0].id, "n1")

        edges = graph.edges_from("n2")
        self.assertEqual(len(edges), 1)
        self.assertEqual(edges[0].relationship, ImpactRelationship.USES)


class TestImpactAnalyzer(unittest.TestCase):
    """Verify bounded, deterministic impact analysis across all evidence cases."""

    def setUp(self):
        self.analyzer = ImpactAnalyzer()

    def test_case_1_function_level_crypto_usage(self):
        """Case 1: RSA -> API -> function -> file (no class)."""
        finding = make_function_level_finding()
        result = self.analyzer.analyze(finding, finding["evidence"])

        self.assertEqual(result.scope, ImpactScope.STATICALLY_OBSERVED)
        node_types = {n.node_type for n in result.nodes}

        # Must establish ALGORITHM, API, FUNCTION, FILE
        self.assertIn(ImpactNodeType.ALGORITHM, node_types)
        self.assertIn(ImpactNodeType.API, node_types)
        self.assertIn(ImpactNodeType.FUNCTION, node_types)
        self.assertIn(ImpactNodeType.FILE, node_types)

        # Critical rule: NEVER fabricate a class when none exists
        self.assertNotIn(ImpactNodeType.CLASS, node_types)

        labels = {n.label for n in result.nodes}
        self.assertIn("RSA", labels)
        self.assertIn("RSAPrivateKey.sign", labels)
        self.assertIn("sign_certificate()", labels)
        self.assertIn("src/signing.py", labels)

        # Verify exact relationships
        relationships = {(r.relationship, r.source_id.split(":")[-2], r.target_id.split(":")[-2]) for r in result.relationships}
        self.assertIn((ImpactRelationship.USES, "api", "algo"), relationships)
        self.assertIn((ImpactRelationship.CALLS, "func", "api"), relationships)
        self.assertIn((ImpactRelationship.DEFINED_IN, "func", "file"), relationships)

    def test_case_2_class_level_crypto_usage(self):
        """Case 2: RSA -> API -> function -> class -> file."""
        finding = make_class_level_finding()
        result = self.analyzer.analyze(finding, finding["evidence"])

        self.assertEqual(result.scope, ImpactScope.STATICALLY_OBSERVED)
        node_types = {n.node_type for n in result.nodes}

        self.assertIn(ImpactNodeType.ALGORITHM, node_types)
        self.assertIn(ImpactNodeType.API, node_types)
        self.assertIn(ImpactNodeType.FUNCTION, node_types)
        self.assertIn(ImpactNodeType.CLASS, node_types)
        self.assertIn(ImpactNodeType.FILE, node_types)

        labels = {n.label for n in result.nodes}
        self.assertIn("CertificateSigner", labels)
        self.assertIn("sign_certificate()", labels)

        relationships = {(r.relationship, r.source_id.split(":")[-2], r.target_id.split(":")[-2]) for r in result.relationships}
        self.assertIn((ImpactRelationship.USES, "api", "algo"), relationships)
        self.assertIn((ImpactRelationship.CALLS, "func", "api"), relationships)
        self.assertIn((ImpactRelationship.CONTAINS, "class", "func"), relationships)
        self.assertIn((ImpactRelationship.DEFINED_IN, "class", "file"), relationships)

    def test_case_3_ambiguous_usage_does_not_invent_relationships(self):
        """Case 3: crypto call at top level without enclosing function or class.

        The engine must not invent relationships or reachability.
        """
        finding = make_ambiguous_finding()
        result = self.analyzer.analyze(finding, finding["evidence"])

        node_types = {n.node_type for n in result.nodes}
        self.assertIn(ImpactNodeType.ALGORITHM, node_types)
        self.assertIn(ImpactNodeType.API, node_types)
        self.assertIn(ImpactNodeType.FILE, node_types)

        # Neither function nor class should be present
        self.assertNotIn(ImpactNodeType.FUNCTION, node_types)
        self.assertNotIn(ImpactNodeType.CLASS, node_types)

        relationships = {(r.relationship, r.source_id.split(":")[-2], r.target_id.split(":")[-2]) for r in result.relationships}
        self.assertIn((ImpactRelationship.USES, "api", "algo"), relationships)
        self.assertIn((ImpactRelationship.DEFINED_IN, "api", "file"), relationships)

    def test_case_4_missing_context_graceful_handling(self):
        """Case 4: missing context (no file, no function).

        The analyzer should gracefully return the maximum impact it can actually establish.
        """
        finding = make_missing_context_finding()
        result = self.analyzer.analyze(finding, None)

        self.assertEqual(result.scope, ImpactScope.STATICALLY_OBSERVED)
        node_types = {n.node_type for n in result.nodes}
        self.assertIn(ImpactNodeType.ALGORITHM, node_types)
        self.assertIn(ImpactNodeType.API, node_types)
        self.assertNotIn(ImpactNodeType.FUNCTION, node_types)
        self.assertNotIn(ImpactNodeType.CLASS, node_types)
        self.assertNotIn(ImpactNodeType.FILE, node_types)

        self.assertEqual(len(result.relationships), 1)
        self.assertEqual(result.relationships[0].relationship, ImpactRelationship.USES)


if __name__ == "__main__":
    unittest.main()
