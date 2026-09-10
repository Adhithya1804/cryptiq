"""The Phase 7 golden fixtures produce exactly the expected observations."""

from pathlib import Path

import pytest

from app.engine.parser import PythonParser
from app.engine.rules import evaluate_file
from tests.golden.expected_phase7 import EXPECTED

GOLDEN = Path(__file__).resolve().parents[1] / "golden"


def observations(name: str):
    path = GOLDEN / name
    parsed = PythonParser().parse(path.read_text(encoding="utf-8"), f"tests/golden/{name}")
    return evaluate_file(parsed)


def as_tuples(matches):
    return tuple(
        (
            match.location.start_line,
            match.rule_id,
            match.algorithm,
            match.api,
            match.operation.value,
            match.confidence.value,
            match.evidence_basis.value,
            match.enclosing_function,
        )
        for match in matches
    )


@pytest.mark.parametrize("name", sorted(EXPECTED))
def test_a_fixture_matches_its_expected_observations(name: str) -> None:
    assert as_tuples(observations(name)) == EXPECTED[name]


@pytest.mark.parametrize("name", sorted(EXPECTED))
def test_every_observation_is_complete(name: str) -> None:
    for match in observations(name):
        assert match.library == "cryptography"
        assert match.ruleset_version == "0.3.0"
        assert match.primitive
        assert match.file_path == f"tests/golden/{name}"
        assert match.location.end_line >= match.location.start_line


@pytest.mark.parametrize("name", sorted(EXPECTED))
def test_a_fixture_is_evaluated_deterministically(name: str) -> None:
    assert as_tuples(observations(name)) == as_tuples(observations(name))


@pytest.mark.parametrize("name", sorted(EXPECTED))
def test_no_call_node_is_reported_twice_by_one_rule(name: str) -> None:
    seen: set[tuple[int, str]] = set()
    for match in observations(name):
        key = (id(match.node), match.rule_id)
        assert key not in seen
        seen.add(key)
