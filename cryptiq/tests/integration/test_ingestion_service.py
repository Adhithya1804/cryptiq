"""The ingestion service verifies, describes and cleans up a snapshot."""

import tempfile
from pathlib import Path

import pytest

from app.engine.discovery import SkipReason
from app.engine.ingestion import (
    IngestionLimits,
    RepositoryReference,
    SourceSnapshot,
    compute_content_hash,
    count_files,
    ingest_commit,
)
from app.errors import InvalidCommitShaError, RepositoryUnavailableError
from tests.support import write_tree

FULL_SHA = "1f903f5ed2e5e316f345a927555e48535829d8de"

REFERENCE = RepositoryReference(
    provider="github",
    owner="pyca",
    name="cryptography",
    canonical_url="https://github.com/pyca/cryptography",
)

TREE = {
    "src/keys.py": b"x = 1\n",
    "src/util.py": b"y = 2\n",
    "README.md": b"# hi\n",
    ".git/HEAD": b"ref: refs/heads/main\n",
}

LIMITS = IngestionLimits(
    max_archive_bytes=1024 * 1024,
    max_extracted_bytes=1024 * 1024,
    max_files=100,
    max_file_bytes=1024,
)


class FakeProvider:
    """A SourceProvider that materialises a fixed tree in a temporary directory."""

    def __init__(self, commit_sha: str = FULL_SHA, files: dict[str, bytes] | None = None) -> None:
        self._commit_sha = commit_sha
        self._files = TREE if files is None else files
        self.root_path: Path | None = None

    async def fetch_commit(
        self, repository: RepositoryReference, commit_sha: str
    ) -> SourceSnapshot:
        root = Path(tempfile.mkdtemp(prefix="cryptiq-source-"))
        write_tree(root, self._files)
        self.root_path = root
        return SourceSnapshot(
            root_path=root,
            repository=repository,
            commit_sha=self._commit_sha,
            content_hash=compute_content_hash(root),
            file_count=count_files(root),
        )


async def test_ingestion_produces_counts_and_a_snapshot() -> None:
    provider = FakeProvider()

    async with ingest_commit(provider, REFERENCE, FULL_SHA, LIMITS) as result:
        assert result.snapshot.root_path.exists()
        assert result.commit_sha == FULL_SHA
        assert result.repository == REFERENCE
        assert len(result.content_hash) == 64
        assert result.total_files == 4
        assert result.analyzed_files == 2
        assert result.skipped_files == 2
        assert result.skipped_reasons == {
            SkipReason.UNSUPPORTED_LANGUAGE: 1,
            SkipReason.IGNORED_PATH: 1,
        }
        assert {file.path for file in result.supported_files} == {
            "src/keys.py",
            "src/util.py",
        }
        assert result.source_state == "LIVE"


async def test_a_short_sha_request_is_satisfied_by_the_full_sha() -> None:
    provider = FakeProvider()

    async with ingest_commit(provider, REFERENCE, "1f903f5", LIMITS) as result:
        assert result.commit_sha == FULL_SHA


async def test_the_temporary_directory_is_removed_afterwards() -> None:
    provider = FakeProvider()

    async with ingest_commit(provider, REFERENCE, FULL_SHA, LIMITS) as result:
        root = result.snapshot.root_path

    assert not root.exists()


async def test_the_temporary_directory_is_removed_when_the_caller_fails() -> None:
    provider = FakeProvider()

    with pytest.raises(ZeroDivisionError):
        async with ingest_commit(provider, REFERENCE, FULL_SHA, LIMITS) as result:
            root = result.snapshot.root_path
            raise ZeroDivisionError

    assert not root.exists()


async def test_a_snapshot_of_another_revision_is_rejected() -> None:
    provider = FakeProvider(commit_sha="b" * 40)

    with pytest.raises(RepositoryUnavailableError):
        async with ingest_commit(provider, REFERENCE, FULL_SHA, LIMITS):
            pass

    assert not provider.root_path.exists()


async def test_an_invalid_sha_never_reaches_the_provider() -> None:
    provider = FakeProvider()

    with pytest.raises(InvalidCommitShaError):
        async with ingest_commit(provider, REFERENCE, "main", LIMITS):
            pass

    assert provider.root_path is None
