"""Provider-neutral validation of revision inputs and returned snapshots."""

import re

from app.engine.ingestion.source import SourceSnapshot
from app.errors import InvalidCommitShaError, RepositoryUnavailableError

FULL_SHA_LENGTH = 40
MIN_SHA_LENGTH = 7

_SHA_PATTERN = re.compile(rf"^[0-9a-fA-F]{{{MIN_SHA_LENGTH},{FULL_SHA_LENGTH}}}$")
_FULL_SHA_PATTERN = re.compile(rf"^[0-9a-f]{{{FULL_SHA_LENGTH}}}$")


def normalize_commit_sha(value: str) -> str:
    """Return the lowercase form of an accepted 7-40 character hexadecimal SHA.

    A short SHA is accepted as input only. The provider must resolve it to the
    full 40-character SHA before a snapshot is produced.
    """
    candidate = value.strip()
    if not _SHA_PATTERN.match(candidate):
        raise InvalidCommitShaError(
            "Commit SHA must be 7 to 40 hexadecimal characters."
        )
    return candidate.lower()


def normalize_full_commit_sha(value: str) -> str:
    """Return a validated lowercase full 40-character SHA."""
    candidate = value.strip().lower()
    if not _FULL_SHA_PATTERN.match(candidate):
        raise RepositoryUnavailableError(
            "The provider returned a revision identifier that is not a full commit SHA."
        )
    return candidate


def verify_snapshot(snapshot: SourceSnapshot, requested_sha: str) -> None:
    """Confirm the snapshot holds the revision that was asked for.

    The provider may resolve a short SHA, so the returned SHA must extend the
    request. Anything else means a branch, a tag or a different commit was
    served, and the snapshot must be rejected rather than analysed.
    """
    resolved = normalize_full_commit_sha(snapshot.commit_sha)
    requested = requested_sha.strip().lower()
    if not resolved.startswith(requested):
        raise RepositoryUnavailableError(
            "The provider returned a different revision than the one requested."
        )
