"""Orchestration of one ingestion, independent of any provider.

The snapshot lives in a temporary directory. ingest_commit owns that directory:
it is handed to the caller for the duration of the analysis and removed when
the context closes, including when the analysis raises.
"""

import logging
import shutil
import time
from collections import Counter
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field

from app.engine.discovery import DiscoveredFile, SkipReason, discover_files
from app.engine.ingestion.limits import IngestionLimits
from app.engine.ingestion.source import (
    RepositoryReference,
    SourceProvider,
    SourceSnapshot,
)
from app.engine.ingestion.validation import normalize_commit_sha, verify_snapshot

logger = logging.getLogger(__name__)

# Matches app.db.models.enums.SourceState. The engine does not import the
# database layer; the scan service maps this value onto the column.
LIVE_SOURCE_STATE = "LIVE"


@dataclass(frozen=True)
class IngestionResult:
    """Everything the next phase needs about an acquired snapshot.

    Deliberately free of database models: the scan service reads these fields
    when it persists a Scan.
    """

    snapshot: SourceSnapshot
    discovered_files: list[DiscoveredFile]
    total_files: int
    analyzed_files: int
    skipped_files: int
    skipped_reasons: dict[SkipReason, int] = field(default_factory=dict)
    source_state: str = LIVE_SOURCE_STATE

    @property
    def commit_sha(self) -> str:
        """The verified full 40-character SHA that was analysed."""
        return self.snapshot.commit_sha

    @property
    def content_hash(self) -> str:
        """The deterministic hash of the retrieved source."""
        return self.snapshot.content_hash

    @property
    def repository(self) -> RepositoryReference:
        """The repository the snapshot came from."""
        return self.snapshot.repository

    @property
    def supported_files(self) -> list[DiscoveredFile]:
        """The files the parser will read in the next phase."""
        return [file for file in self.discovered_files if file.is_supported]


def build_result(snapshot: SourceSnapshot, limits: IngestionLimits) -> IngestionResult:
    """Discover the snapshot's files and summarise them."""
    discovered = discover_files(snapshot.root_path, limits.max_file_bytes)
    analyzed = sum(1 for file in discovered if file.is_supported)
    reasons = Counter(file.skip_reason for file in discovered if file.skip_reason is not None)
    return IngestionResult(
        snapshot=snapshot,
        discovered_files=discovered,
        total_files=len(discovered),
        analyzed_files=analyzed,
        skipped_files=len(discovered) - analyzed,
        skipped_reasons=dict(reasons),
    )


def cleanup_snapshot(snapshot: SourceSnapshot) -> None:
    """Remove the snapshot's temporary directory."""
    shutil.rmtree(snapshot.root_path, ignore_errors=True)


@asynccontextmanager
async def ingest_commit(
    provider: SourceProvider,
    repository: RepositoryReference,
    commit_sha: str,
    limits: IngestionLimits | None = None,
) -> AsyncIterator[IngestionResult]:
    """Acquire, verify and describe one exact revision.

    Yields the result while the extracted source is on disk, then removes it.
    """
    limits = limits or IngestionLimits.from_settings()
    requested = normalize_commit_sha(commit_sha)
    started = time.monotonic()

    snapshot = await provider.fetch_commit(repository, requested)
    try:
        verify_snapshot(snapshot, requested)
        result = build_result(snapshot, limits)
        logger.info(
            "ingested %s at %s: %d files, %d analyzable, in %.2fs",
            repository.slug,
            snapshot.commit_sha,
            result.total_files,
            result.analyzed_files,
            time.monotonic() - started,
        )
        yield result
    finally:
        cleanup_snapshot(snapshot)
