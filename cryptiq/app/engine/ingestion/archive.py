"""Safe extraction of an untrusted ZIP archive.

Every member path is validated before a single byte is written, and the total
extracted size is checked as the bytes arrive. Symbolic links are validated and
then skipped rather than recreated. Nothing in the archive is ever executed.
"""

import posixpath
import re
import stat
import zipfile
from pathlib import Path, PurePosixPath

from app.engine.ingestion.limits import IngestionLimits
from app.errors import MalformedArchiveError, UnsafeArchiveError

_CHUNK_BYTES = 512 * 1024
# A link target is a path; anything longer is not one worth decompressing.
_MAX_SYMLINK_TARGET_BYTES = 4096
_WINDOWS_DRIVE = re.compile(r"^[A-Za-z]:")


def _reject(reason: str, member: str) -> UnsafeArchiveError:
    return UnsafeArchiveError(f"Archive entry {member!r} rejected: {reason}.")


def safe_relative_path(member: str) -> PurePosixPath:
    """Return the member's path, or raise if it could escape the root.

    Rejects absolute POSIX paths, Windows drive letters and UNC paths,
    backslash separators, and any ".." component.
    """
    if not member or member in {".", "./"}:
        raise _reject("empty path", member)
    if "\\" in member:
        raise _reject("backslash path separator", member)
    if member.startswith("/") or _WINDOWS_DRIVE.match(member):
        raise _reject("absolute path", member)

    path = PurePosixPath(member)
    if path.is_absolute():
        raise _reject("absolute path", member)
    parts = [part for part in path.parts if part not in {".", ""}]
    if any(part == ".." for part in parts):
        raise _reject("parent directory traversal", member)
    if not parts:
        raise _reject("empty path", member)
    return PurePosixPath(*parts)


def _is_symlink(info: zipfile.ZipInfo) -> bool:
    """Return True if the member declares itself a symbolic link."""
    return stat.S_IFMT(info.external_attr >> 16) == stat.S_IFLNK


def _assert_supported_member(info: zipfile.ZipInfo) -> None:
    """Reject a socket, device or FIFO member.

    Many writers store permission bits without a file type, so only an
    explicitly declared type is judged.
    """
    file_type = stat.S_IFMT(info.external_attr >> 16)
    if file_type in {0, stat.S_IFREG, stat.S_IFDIR, stat.S_IFLNK}:
        return
    raise _reject("not a regular file, directory or symbolic link", info.filename)


def _assert_symlink_stays_inside(
    archive: zipfile.ZipFile, info: zipfile.ZipInfo, relative: PurePosixPath
) -> None:
    """Reject a symbolic link that points outside the extraction root.

    Links are validated but never recreated. Real repositories contain
    in-tree links, and refusing those would reject most archives; a link that
    escapes the root is the hostile case and fails the whole extraction.
    """
    with archive.open(info) as handle:
        target = handle.read(_MAX_SYMLINK_TARGET_BYTES).decode("utf-8", errors="replace")
    if target.startswith("/") or _WINDOWS_DRIVE.match(target):
        raise _reject("symbolic link to an absolute path", info.filename)

    resolved = PurePosixPath(
        posixpath.normpath(posixpath.join(relative.parent.as_posix(), target))
    )
    if resolved.parts and resolved.parts[0] == "..":
        raise _reject("symbolic link escaping the extraction root", info.filename)


def _assert_within(destination: Path, target: Path, member: str) -> None:
    resolved_root = destination.resolve()
    resolved_target = target.resolve()
    if resolved_target != resolved_root and resolved_root not in resolved_target.parents:
        raise _reject("path escapes the extraction root", member)


def _common_top_level(names: list[str]) -> str | None:
    """Return the single top-level directory shared by every member, if any.

    A GitHub archive wraps the tree in one "owner-repo-sha" directory. Stripping
    it makes the extraction root the repository root.
    """
    tops = {PurePosixPath(name).parts[0] for name in names if PurePosixPath(name).parts}
    if len(tops) != 1:
        return None
    top = tops.pop()
    if any(PurePosixPath(name) == PurePosixPath(top) and not name.endswith("/") for name in names):
        return None
    return top


def extract_zip(
    archive_path: Path,
    destination: Path,
    limits: IngestionLimits,
    *,
    strip_top_level: bool = True,
) -> int:
    """Extract archive_path into destination and return the file count.

    Raises UnsafeArchiveError, ArchiveTooLargeError or MalformedArchiveError.
    The caller is responsible for removing destination when extraction fails.
    """
    destination.mkdir(parents=True, exist_ok=True)

    try:
        with zipfile.ZipFile(archive_path) as archive:
            # The whole archive is never decompressed up front: a CRC pass over
            # every member would be the zip bomb the limits exist to stop.
            infos = archive.infolist()
            prefix = (
                _common_top_level([info.filename for info in infos])
                if strip_top_level
                else None
            )
            return _extract_members(archive, infos, destination, limits, prefix)
    except (zipfile.BadZipFile, EOFError) as exc:
        raise MalformedArchiveError("Archive is not a readable ZIP file.") from exc


def _extract_members(
    archive: zipfile.ZipFile,
    infos: list[zipfile.ZipInfo],
    destination: Path,
    limits: IngestionLimits,
    prefix: str | None,
) -> int:
    files = [info for info in infos if not info.is_dir()]
    limits.check_file_count(len(files))

    for info in files:
        safe_relative_path(info.filename)
    limits.check_extracted_bytes(sum(info.file_size for info in files))

    extracted_total = 0
    file_count = 0
    for info in infos:
        _assert_supported_member(info)
        relative = safe_relative_path(info.filename)
        if prefix is not None:
            if relative.parts[0] != prefix:
                raise _reject("outside the archive's top-level directory", info.filename)
            relative = PurePosixPath(*relative.parts[1:])
            if not relative.parts:
                continue

        if _is_symlink(info):
            _assert_symlink_stays_inside(archive, info, relative)
            continue

        target = destination / Path(*relative.parts)
        _assert_within(destination, target, info.filename)

        if info.is_dir():
            target.mkdir(parents=True, exist_ok=True)
            continue

        target.parent.mkdir(parents=True, exist_ok=True)
        extracted_total += _write_member(archive, info, target, limits, extracted_total)
        file_count += 1

    return file_count


def _write_member(
    archive: zipfile.ZipFile,
    info: zipfile.ZipInfo,
    target: Path,
    limits: IngestionLimits,
    already_extracted: int,
) -> int:
    """Stream one member to disk, checking the total as the bytes arrive.

    The running total is what stops a compressed bomb: a member may declare a
    small size in its header and then decompress to far more.
    """
    written = 0
    with archive.open(info) as source, target.open("wb") as sink:
        while chunk := source.read(_CHUNK_BYTES):
            written += len(chunk)
            limits.check_extracted_bytes(already_extracted + written)
            sink.write(chunk)
    return written
