"""The golden fixtures produce exactly the expected observations."""

from pathlib import Path

import pytest

from app.engine.parser import PythonParser
from app.engine.rules import evaluate_file
from tests.golden.expected import EXPECTED

GOLDEN = Path(__file__).resolve().parents[1] / "golden"


def observations(name: str):
    path = GOLDEN / name
    parsed = PythonParser().parse(path.read_text(encoding="utf-8"), f"tests/golden/{name}")
    return evaluate_file(parsed)


def as_tuples(matches):
    return tuple(
        (
            match.location.start_line,
            match.api,
            match.operation.value,
            match.confidence.value,
            match.evidence_basis.value,
            match.enclosing_function,
            match.enclosing_class,
        )
        for match in matches
    )


@pytest.mark.parametrize("name", sorted(EXPECTED))
def test_a_fixture_matches_its_expected_observations(name: str) -> None:
    assert as_tuples(observations(name)) == EXPECTED[name]


@pytest.mark.parametrize("name", sorted(EXPECTED))
def test_every_observation_is_a_complete_rsa_record(name: str) -> None:
    for match in observations(name):
        assert match.rule_id == "PY-CRYPTO-RSA"
        assert match.algorithm == "RSA"
        assert match.primitive == "RSA"
        assert match.library == "cryptography"
        assert match.ruleset_version == "0.3.0"
        assert match.file_path == f"tests/golden/{name}"
        assert match.location.end_line >= match.location.start_line


@pytest.mark.parametrize("name", sorted(EXPECTED))
def test_a_fixture_is_evaluated_deterministically(name: str) -> None:
    assert as_tuples(observations(name)) == as_tuples(observations(name))
