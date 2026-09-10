"""Commit SHA input rules and snapshot revision verification."""

from pathlib import Path

import pytest

from app.engine.ingestion.source import RepositoryReference, SourceSnapshot
from app.engine.ingestion.validation import (
    normalize_commit_sha,
    normalize_full_commit_sha,
    verify_snapshot,
)
from app.errors import InvalidCommitShaError, RepositoryUnavailableError

FULL_SHA = "1f903f5ed2e5e316f345a927555e48535829d8de"

REFERENCE = RepositoryReference(
    provider="github",
    owner="pyca",
    name="cryptography",
    canonical_url="https://github.com/pyca/cryptography",
)


def _snapshot(commit_sha: str) -> SourceSnapshot:
    return SourceSnapshot(
        root_path=Path("/tmp/does-not-need-to-exist"),
        repository=REFERENCE,
        commit_sha=commit_sha,
        content_hash="0" * 64,
        file_count=1,
    )


def test_full_sha_is_accepted() -> None:
    assert normalize_commit_sha(FULL_SHA) == FULL_SHA


def test_short_sha_is_accepted() -> None:
    assert normalize_commit_sha("1f903f5") == "1f903f5"


def test_sha_is_lowercased_and_trimmed() -> None:
    assert normalize_commit_sha(f"  {FULL_SHA.upper()}  ") == FULL_SHA


@pytest.mark.parametrize(
    "value",
    [
        "",
        "1f903f",
        FULL_SHA + "a",
        "1f903f5ed2e5e316f345a927555e48535829d8dz",
        "main",
        "HEAD",
        "refs/heads/main",
        "1f903f5 ; rm -rf /",
    ],
)
def test_invalid_shas_are_rejected(value: str) -> None:
    with pytest.raises(InvalidCommitShaError):
        normalize_commit_sha(value)


def test_resolved_sha_must_be_a_full_sha() -> None:
    assert normalize_full_commit_sha(FULL_SHA.upper()) == FULL_SHA

    with pytest.raises(RepositoryUnavailableError):
        normalize_full_commit_sha("1f903f5")


def test_snapshot_matching_the_full_request_is_accepted() -> None:
    verify_snapshot(_snapshot(FULL_SHA), FULL_SHA)


def test_snapshot_matching_a_short_request_is_accepted() -> None:
    verify_snapshot(_snapshot(FULL_SHA), "1f903f5")


def test_snapshot_holding_a_different_revision_is_rejected() -> None:
    with pytest.raises(RepositoryUnavailableError):
        verify_snapshot(_snapshot("b" * 40), FULL_SHA)


def test_snapshot_without_a_full_sha_is_rejected() -> None:
    with pytest.raises(RepositoryUnavailableError):
        verify_snapshot(_snapshot("main"), "1f903f5")
