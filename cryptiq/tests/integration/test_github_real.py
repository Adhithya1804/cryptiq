"""Opt-in end-to-end retrieval of a real commit from GitHub.

Enable with CRYPTIQ_RUN_NETWORK_TESTS=1. The rest of the suite must never
depend on GitHub being reachable, so this module skips by default.
"""

import os

import pytest

from app.engine.ingestion import ingest_commit
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


async def test_the_exact_commit_is_retrieved_and_analysable() -> None:
    repository = parse_repository_url(REPOSITORY_URL)
    provider = GitHubSourceProvider()

    async with ingest_commit(provider, repository, COMMIT_SHA) as result:
        assert result.snapshot.root_path.is_dir()
        assert result.commit_sha == COMMIT_SHA
        assert result.snapshot.file_count > 0
        assert result.total_files > 0
        assert result.analyzed_files > 0
        assert any(file.path.endswith(".py") for file in result.supported_files)
        assert (result.snapshot.root_path / "src" / "cryptography").is_dir()
        assert len(result.content_hash) == 64
        root = result.snapshot.root_path

    assert not root.exists()


async def test_a_short_sha_resolves_to_the_same_revision() -> None:
    repository = parse_repository_url(REPOSITORY_URL)
    provider = GitHubSourceProvider()

    async with ingest_commit(provider, repository, COMMIT_SHA[:7]) as result:
        assert result.commit_sha == COMMIT_SHA
