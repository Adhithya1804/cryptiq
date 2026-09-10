"""Walking an extracted source tree.

Shared by the stages that read a snapshot from disk, so they agree on what
counts as a file.
"""

from collections.abc import Iterator
from pathlib import Path


def iter_files(root: Path) -> Iterator[Path]:
    """Yield every regular file under root in path order, skipping symlinks.

    Symlinks are skipped rather than followed: a snapshot must describe the
    bytes that were retrieved, and following a link could leave the root.
    """
    for path in sorted(root.rglob("*")):
        if path.is_symlink() or not path.is_file():
            continue
        yield path
