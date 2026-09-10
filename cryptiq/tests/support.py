"""Helpers for building the archives and trees the ingestion tests need."""

import io
import stat
import struct
import zipfile
from pathlib import Path

TOP_LEVEL = "owner-repo-abc1234"


def build_zip(entries: dict[str, bytes], *, top_level: str | None = TOP_LEVEL) -> bytes:
    """Return a ZIP holding the given entries, optionally under one root directory."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, payload in entries.items():
            full_name = f"{top_level}/{name}" if top_level else name
            archive.writestr(full_name, payload)
    return buffer.getvalue()


def build_raw_zip(names: list[str], payload: bytes = b"x") -> bytes:
    """Return a ZIP whose member names are written exactly as given."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name in names:
            archive.writestr(name, payload)
    return buffer.getvalue()


def build_symlink_zip(link_name: str, target: str) -> bytes:
    """Return a ZIP holding a symbolic link entry beside a regular file."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        info = zipfile.ZipInfo(link_name)
        info.create_system = 3  # Unix
        info.external_attr = (stat.S_IFLNK | 0o777) << 16
        archive.writestr(info, target)
        archive.writestr("regular.py", b"x = 1\n")
    return buffer.getvalue()


def write_tree(root: Path, files: dict[str, bytes]) -> Path:
    """Write a file tree under root and return root."""
    for relative_path, payload in files.items():
        target = root / relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(payload)
    return root


def build_understated_zip(name: str, payload: bytes) -> bytes:
    """Return a ZIP whose headers claim a member is one byte long.

    Both the local header and the central directory record the uncompressed
    size, so a bomb can declare almost nothing and expand on extraction. The
    true size is rewritten here to exercise the check that runs while the
    bytes are being written.
    """
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(name, payload)

    raw = buffer.getvalue()
    true_size = struct.pack("<I", len(payload))
    if raw.count(true_size) != 2:
        raise AssertionError("expected the size field in the local and central headers")
    return raw.replace(true_size, struct.pack("<I", 1))
