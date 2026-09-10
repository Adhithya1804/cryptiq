"""The bounded impact graph describes only what the parse established."""

import pytest

from app.engine.impact import ImpactNodeType, ImpactRelationship, ImpactScope, analyze
from app.engine.parser import PythonParser
from app.engine.rules import MatchConfidence, evaluate_file

IMPORT = "from cryptography.hazmat.primitives.asymmetric import rsa\n"


def first_match(source: str, path: str = "src/signing.py"):
    parsed = PythonParser().parse(source, path)
    return evaluate_file(parsed)[0], parsed


def labels(result, node_type: ImpactNodeType) -> list[str]:
    return [node.label for node in result.nodes_of(node_type)]


def test_a_method_call_produces_the_full_chain() -> None:
    match, parsed = first_match(
        IMPORT
        + "class Signer:\n"
        + "    def sign(self, key: rsa.RSAPrivateKey, payload):\n"
        + "        return key.sign(payload)\n"
    )

    result = analyze(match, parsed.module_path)

    assert [node.node_type for node in result.nodes] == [
        ImpactNodeType.ALGORITHM,
        ImpactNodeType.API,
        ImpactNodeType.FUNCTION,
        ImpactNodeType.CLASS,
        ImpactNodeType.MODULE,
        ImpactNodeType.FILE,
    ]
    assert labels(result, ImpactNodeType.ALGORITHM) == ["RSA"]
    assert labels(result, ImpactNodeType.API) == ["RSAPrivateKey.sign"]
    assert labels(result, ImpactNodeType.FUNCTION) == ["Signer.sign"]
    assert labels(result, ImpactNodeType.CLASS) == ["Signer"]
    assert labels(result, ImpactNodeType.MODULE) == ["src.signing"]
    assert labels(result, ImpactNodeType.FILE) == ["src/signing.py"]


def test_the_relationships_point_outwards_from_the_algorithm() -> None:
    match, parsed = first_match(
        IMPORT
        + "class Signer:\n"
        + "    def sign(self, key: rsa.RSAPrivateKey, payload):\n"
        + "        return key.sign(payload)\n"
    )

    result = analyze(match, parsed.module_path)
    edges = {
        (edge.source_id, edge.target_id, edge.relationship) for edge in result.relationships
    }

    assert ("API:RSAPrivateKey.sign", "ALGORITHM:RSA", ImpactRelationship.USES) in edges
    assert (
        "FUNCTION:Signer.sign",
        "API:RSAPrivateKey.sign",
        ImpactRelationship.CALLS,
    ) in edges
    assert ("CLASS:Signer", "FUNCTION:Signer.sign", ImpactRelationship.CONTAINS) in edges
    assert (
        "MODULE:src.signing",
        "FILE:src/signing.py",
        ImpactRelationship.DEFINED_IN,
    ) in edges


def test_a_missing_class_is_absent_rather_than_invented() -> None:
    match, parsed = first_match(IMPORT + "def build():\n    return rsa.generate_private_key()\n")

    result = analyze(match, parsed.module_path)

    assert result.nodes_of(ImpactNodeType.CLASS) == ()
    assert labels(result, ImpactNodeType.FUNCTION) == ["build"]


def test_a_module_level_call_has_no_function_node() -> None:
    match, parsed = first_match(IMPORT + "key = rsa.generate_private_key()\n")

    result = analyze(match, parsed.module_path)

    assert result.nodes_of(ImpactNodeType.FUNCTION) == ()
    assert result.nodes_of(ImpactNodeType.CLASS) == ()
    assert labels(result, ImpactNodeType.ALGORITHM) == ["RSA"]


def test_a_snapshot_without_a_module_path_omits_the_module_node() -> None:
    match, _ = first_match(IMPORT + "key = rsa.generate_private_key()\n", "not-a-module.py")

    result = analyze(match, None)

    assert result.nodes_of(ImpactNodeType.MODULE) == ()
    assert labels(result, ImpactNodeType.FILE) == ["not-a-module.py"]


def test_the_scope_is_never_widened_beyond_what_was_observed() -> None:
    match, parsed = first_match(IMPORT + "key = rsa.generate_private_key()\n")

    assert analyze(match, parsed.module_path).scope is ImpactScope.STATICALLY_OBSERVED


def test_the_confidence_comes_from_the_match() -> None:
    source = (
        IMPORT
        + "def sign(payload):\n"
        + "    key = rsa.generate_private_key()\n"
        + "    return key.sign(payload)\n"
    )
    parsed = PythonParser().parse(source, "src/signing.py")
    generation, signing = evaluate_file(parsed)

    assert analyze(generation, parsed.module_path).confidence is MatchConfidence.HIGH
    assert analyze(signing, parsed.module_path).confidence is MatchConfidence.MEDIUM


def test_the_graph_is_identical_across_runs() -> None:
    match, parsed = first_match(IMPORT + "key = rsa.generate_private_key()\n")

    assert analyze(match, parsed.module_path) == analyze(match, parsed.module_path)


def test_node_identifiers_carry_no_random_value() -> None:
    match, parsed = first_match(IMPORT + "key = rsa.generate_private_key()\n")

    identifiers = [node.id for node in analyze(match, parsed.module_path).nodes]

    assert identifiers == [
        "ALGORITHM:RSA",
        "API:rsa.generate_private_key",
        "MODULE:src.signing",
        "FILE:src/signing.py",
    ]


def test_a_repeated_relationship_does_not_inflate_the_graph() -> None:
    from app.engine.impact import ImpactGraph, ImpactNode

    graph = ImpactGraph()
    for identifier, node_type in (("a", ImpactNodeType.API), ("b", ImpactNodeType.FILE)):
        graph.add_node(
            ImpactNode(
                id=identifier,
                node_type=node_type,
                label=identifier,
                relationship=None,
                confidence=MatchConfidence.HIGH,
            )
        )
    for _ in range(3):
        graph.add_edge("a", "b", ImpactRelationship.USES, MatchConfidence.HIGH)

    result = graph.to_result(ImpactScope.STATICALLY_OBSERVED, MatchConfidence.HIGH)
    assert len(result.relationships) == 1
    assert result.node_count == 2


def test_an_edge_to_an_unknown_node_is_refused() -> None:
    from app.engine.impact import ImpactGraph

    with pytest.raises(KeyError):
        ImpactGraph().add_edge("a", "b", ImpactRelationship.USES, MatchConfidence.HIGH)
