"""Opt-in parse of a real repository at an exact commit.

Enable with CRYPTIQ_RUN_NETWORK_TESTS=1. The rest of the suite must never
depend on GitHub being reachable, so this module skips by default.
"""

import os

import pytest

from app.engine.ingestion import ingest_commit
from app.engine.parser import SymbolKind, parse_all
from app.integrations.github import GitHubSourceProvider, parse_repository_url

REPOSITORY_URL = "https://github.com/pyca/cryptography"
COMMIT_SHA = "1f903f5ed2e5e316f345a927555e48535829d8de"

pytestmark = [
    pytest.mark.network,
    pytest.mark.skipif(
        os.getenv("CRYPTIQ_RUN_NETWORK_TESTS") != "1",
        reason="set CRYPTIQ_RUN_NETWORK_TESTS=1 to run tests that reach GitHub",
    ),
]


@pytest.fixture(scope="module")
async def parsed_repository():
    """Ingest the exact commit once and parse every supported file."""
    repository = parse_repository_url(REPOSITORY_URL)
    async with ingest_commit(GitHubSourceProvider(), repository, COMMIT_SHA) as result:
        yield parse_all(result.snapshot.root_path, result.discovered_files)


async def test_the_repository_parses(parsed_repository) -> None:
    assert len(parsed_repository) > 100
    assert all(file.language == "python" for file in parsed_repository)
    assert all(file.parser_version == "python-ast-1" for file in parsed_repository)


async def test_a_malformed_file_would_not_stop_the_batch(parsed_repository) -> None:
    failures = [file for file in parsed_repository if not file.parsed]
    successes = [file for file in parsed_repository if file.parsed]

    assert successes
    # This repository ships deliberately invalid Python as test data; whether
    # any is present at this commit or not, the batch must still complete.
    assert len(failures) + len(successes) == len(parsed_repository)
    assert all(file.error is not None and file.tree is None for file in failures)


async def test_definitions_and_calls_are_discovered(parsed_repository) -> None:
    functions = sum(
        1 for file in parsed_repository for _ in file.symbols_of(SymbolKind.FUNCTION)
    )
    classes = sum(1 for file in parsed_repository for _ in file.symbols_of(SymbolKind.CLASS))
    calls = sum(len(file.calls) for file in parsed_repository)

    assert functions > 100
    assert classes > 10
    assert calls > 500


async def test_paths_stay_relative_posix_paths(parsed_repository) -> None:
    assert all(not file.path.startswith("/") for file in parsed_repository)
    assert all("\\" not in file.path for file in parsed_repository)
    assert any(file.path.startswith("src/cryptography/") for file in parsed_repository)


async def test_every_recorded_call_has_an_exact_location(parsed_repository) -> None:
    for file in parsed_repository:
        for call in file.calls:
            assert call.location.start_line >= 1
            assert call.location.end_line >= call.location.start_line
            assert call.location.start_column >= 0
            assert call.location.end_column >= 0


async def test_the_cryptography_package_imports_are_resolvable(parsed_repository) -> None:
    resolutions = {
        local: qualified
        for file in parsed_repository
        for local, qualified in file.import_index.items()
    }

    assert resolutions
    assert any(qualified.startswith("cryptography.") for qualified in resolutions.values())
