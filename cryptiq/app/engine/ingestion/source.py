"""Provider-neutral source types.

The analysis engine consumes a SourceSnapshot and nothing else. It never learns
which provider produced it, so a GitHub archive, a local directory and a future
provider are interchangeable below this line.
"""

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from app.engine.tree import iter_files

CONTENT_HASH_ALGORITHM = "sha256"
_CHUNK_BYTES = 1024 * 1024


@dataclass(frozen=True)
class RepositoryReference:
    """A repository identified the way the database identifies it.

    provider, owner and name are the Phase 2 lookup key; canonical_url is the
    normalized form of whatever URL the user supplied.
    """

    provider: str
    owner: str
    name: str
    canonical_url: str

    @property
    def slug(self) -> str:
        """Return "owner/name", the form used in logs and content hashes."""
        return f"{self.owner}/{self.name}"


@dataclass(frozen=True)
class SourceSnapshot:
    """An extracted, verified copy of one exact revision.

    root_path is a temporary directory owned by whoever ran the ingestion; it
    stays alive for the duration of the analysis and is removed afterwards.
    """

    root_path: Path
    repository: RepositoryReference
    commit_sha: str
    content_hash: str
    file_count: int


class SourceProvider(Protocol):
    """Acquires an exact revision of a repository."""

    async def fetch_commit(
        self,
        repository: RepositoryReference,
        commit_sha: str,
    ) -> SourceSnapshot:
        """Return a snapshot of the requested revision, or raise IngestionError."""
        ...


def _file_digest(path: Path) -> str:
    digest = hashlib.new(CONTENT_HASH_ALGORITHM)
    with path.open("rb") as handle:
        while chunk := handle.read(_CHUNK_BYTES):
            digest.update(chunk)
    return digest.hexdigest()


def compute_content_hash(root: Path) -> str:
    """Return a deterministic hash of every file under root.

    Convention, fixed so the same commit always hashes the same way:

    1. Collect every regular file under root, excluding symlinks.
    2. Express each path relative to root with forward slashes.
    3. Sort those relative paths as byte strings, ascending.
    4. For each file, append to a running SHA-256:
       relative path (UTF-8), a NUL byte, the file's SHA-256 hex digest, a
       newline.
    5. The final SHA-256 hex digest is the content hash.

    Only path names and file bytes take part, so the hash does not depend on
    the temporary directory, timestamps, permissions or extraction order.
    """
    digest = hashlib.new(CONTENT_HASH_ALGORITHM)
    entries = sorted(
        (path.relative_to(root).as_posix(), path) for path in iter_files(root)
    )
    for relative_path, path in entries:
        digest.update(relative_path.encode("utf-8"))
        digest.update(b"\x00")
        digest.update(_file_digest(path).encode("ascii"))
        digest.update(b"\n")
    return digest.hexdigest()


def count_files(root: Path) -> int:
    """Return the number of regular files under root."""
    return sum(1 for _ in iter_files(root))
