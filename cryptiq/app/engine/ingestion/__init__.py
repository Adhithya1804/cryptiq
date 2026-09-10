"""Ingestion: resolve a repository reference to an exact commit and fetch its source snapshot."""

from app.engine.ingestion.limits import IngestionLimits
from app.engine.ingestion.service import (
    IngestionResult,
    build_result,
    cleanup_snapshot,
    ingest_commit,
)
from app.engine.ingestion.source import (
    RepositoryReference,
    SourceProvider,
    SourceSnapshot,
    compute_content_hash,
    count_files,
)
from app.engine.ingestion.validation import normalize_commit_sha, verify_snapshot

__all__ = [
    "IngestionLimits",
    "IngestionResult",
    "RepositoryReference",
    "SourceProvider",
    "SourceSnapshot",
    "build_result",
    "cleanup_snapshot",
    "compute_content_hash",
    "count_files",
    "ingest_commit",
    "normalize_commit_sha",
    "verify_snapshot",
]
