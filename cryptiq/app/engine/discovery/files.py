"""File discovery over an extracted source snapshot.

Discovery decides which files the parser will later read. It never opens a file
as code and never executes anything; it only measures and classifies. Every
file is accounted for: a file is either supported or carries a skip reason.
"""

import logging
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from app.engine.tree import iter_files

logger = logging.getLogger(__name__)

PYTHON_SUFFIX = ".py"
PYTHON_LANGUAGE = "python"
_BINARY_PROBE_BYTES = 8192

# Only repository metadata is ignored. Directories that merely look like build
# output (build/, dist/, venv/) are left in: they can hold real source, and
# silently dropping them would understate the analysed surface.
IGNORED_DIRECTORIES = frozenset({".git"})


class SkipReason(StrEnum):
    """Why a discovered file will not be parsed."""

    UNSUPPORTED_LANGUAGE = "UNSUPPORTED_LANGUAGE"
    BINARY_FILE = "BINARY_FILE"
    TOO_LARGE = "TOO_LARGE"
    INVALID_ENCODING = "INVALID_ENCODING"
    IGNORED_PATH = "IGNORED_PATH"


@dataclass(frozen=True)
class DiscoveredFile:
    """One file in the snapshot and the decision made about it."""

    path: str
    language: str | None
    size: int
    is_binary: bool
    is_supported: bool
    skip_reason: SkipReason | None


def _is_ignored(relative_path: Path) -> bool:
    return any(part in IGNORED_DIRECTORIES for part in relative_path.parts)


def _looks_binary(path: Path) -> bool:
    """Return True if the file's first bytes contain a NUL."""
    with path.open("rb") as handle:
        return b"\x00" in handle.read(_BINARY_PROBE_BYTES)


def _is_valid_utf8(path: Path) -> bool:
    try:
        path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, ValueError):
        return False
    return True


def classify_file(path: Path, relative_path: Path, max_file_bytes: int) -> DiscoveredFile:
    """Classify one file without parsing it.

    Checks run cheapest first: path, then extension, then size, then the two
    that must read bytes.
    """
    posix_path = relative_path.as_posix()
    size = path.stat().st_size

    def skipped(reason: SkipReason, *, language: str | None, is_binary: bool) -> DiscoveredFile:
        return DiscoveredFile(
            path=posix_path,
            language=language,
            size=size,
            is_binary=is_binary,
            is_supported=False,
            skip_reason=reason,
        )

    if _is_ignored(relative_path):
        return skipped(SkipReason.IGNORED_PATH, language=None, is_binary=False)

    if path.suffix != PYTHON_SUFFIX:
        return skipped(SkipReason.UNSUPPORTED_LANGUAGE, language=None, is_binary=False)

    if size > max_file_bytes:
        return skipped(SkipReason.TOO_LARGE, language=PYTHON_LANGUAGE, is_binary=False)

    if _looks_binary(path):
        return skipped(SkipReason.BINARY_FILE, language=PYTHON_LANGUAGE, is_binary=True)

    if not _is_valid_utf8(path):
        return skipped(SkipReason.INVALID_ENCODING, language=PYTHON_LANGUAGE, is_binary=False)

    return DiscoveredFile(
        path=posix_path,
        language=PYTHON_LANGUAGE,
        size=size,
        is_binary=False,
        is_supported=True,
        skip_reason=None,
    )


def discover_files(root: Path, max_file_bytes: int) -> list[DiscoveredFile]:
    """Classify every regular file under root, ordered by relative path.

    Takes a plain path rather than a snapshot: discovery reads a directory and
    knows nothing about how that directory was acquired.
    """
    discovered = [
        classify_file(path, path.relative_to(root), max_file_bytes)
        for path in iter_files(root)
    ]
    logger.debug("classified %d files under %s", len(discovered), root)
    return discovered
