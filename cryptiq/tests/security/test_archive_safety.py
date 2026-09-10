"""Every unsafe archive must fail before anything lands outside the root."""

import zipfile
from dataclasses import replace
from pathlib import Path

import pytest

from app.engine.discovery import SkipReason, discover_files
from app.engine.ingestion.archive import extract_zip, safe_relative_path
from app.engine.ingestion.limits import IngestionLimits
from app.errors import ArchiveTooLargeError, MalformedArchiveError, UnsafeArchiveError
from tests.support import (
    build_raw_zip,
    build_symlink_zip,
    build_understated_zip,
    build_zip,
)

LIMITS = IngestionLimits(
    max_archive_bytes=1024 * 1024,
    max_extracted_bytes=1024 * 1024,
    max_files=100,
    max_file_bytes=64 * 1024,
)


def _write(tmp_path: Path, payload: bytes) -> Path:
    archive_path = tmp_path / "archive.zip"
    archive_path.write_bytes(payload)
    return archive_path


def test_a_normal_archive_extracts_with_the_top_level_stripped(tmp_path: Path) -> None:
    archive = _write(tmp_path, build_zip({"src/keys.py": b"x = 1\n", "README.md": b"hi"}))
    destination = tmp_path / "out"

    count = extract_zip(archive, destination, LIMITS)

    assert count == 2
    assert (destination / "src" / "keys.py").read_bytes() == b"x = 1\n"
    assert not (destination / "owner-repo-abc1234").exists()


@pytest.mark.parametrize(
    "member",
    [
        "../escape.py",
        "../../escape.py",
        "foo/../../secret.py",
        "/etc/passwd",
        "C:/Windows/system32/config",
        "C:\\Windows\\system32\\config",
        "..\\escape.py",
        "foo\\bar.py",
    ],
)
def test_traversal_and_absolute_members_are_rejected(member: str) -> None:
    with pytest.raises(UnsafeArchiveError):
        safe_relative_path(member)


@pytest.mark.parametrize(
    "member",
    ["../escape.py", "foo/../../secret.py", "/etc/passwd", "..\\escape.py"],
)
def test_unsafe_archives_do_not_extract(tmp_path: Path, member: str) -> None:
    archive = _write(tmp_path, build_raw_zip([member]))
    destination = tmp_path / "out"

    with pytest.raises(UnsafeArchiveError):
        extract_zip(archive, destination, LIMITS)

    assert not (tmp_path / "escape.py").exists()
    assert not (tmp_path.parent / "secret.py").exists()


def test_a_symlink_to_an_absolute_path_is_rejected(tmp_path: Path) -> None:
    archive = _write(tmp_path, build_symlink_zip("link", "/etc/passwd"))
    destination = tmp_path / "out"

    with pytest.raises(UnsafeArchiveError):
        extract_zip(archive, destination, LIMITS)

    assert not (destination / "link").exists()


def test_a_symlink_escaping_the_root_is_rejected(tmp_path: Path) -> None:
    archive = _write(tmp_path, build_symlink_zip("nested/link", "../../../../etc/passwd"))

    with pytest.raises(UnsafeArchiveError):
        extract_zip(archive, tmp_path / "out", LIMITS)


def test_an_in_tree_symlink_is_skipped_rather_than_recreated(tmp_path: Path) -> None:
    archive = _write(tmp_path, build_symlink_zip("CLAUDE.md", "AGENTS.md"))
    destination = tmp_path / "out"

    count = extract_zip(archive, destination, LIMITS)

    assert count == 1
    assert (destination / "regular.py").exists()
    assert not (destination / "CLAUDE.md").exists()
    assert not (destination / "CLAUDE.md").is_symlink()


def test_a_nested_symlink_pointing_back_inside_the_root_is_skipped(tmp_path: Path) -> None:
    archive = _write(tmp_path, build_symlink_zip("docs/link.py", "../regular.py"))
    destination = tmp_path / "out"

    extract_zip(archive, destination, LIMITS)

    assert not (destination / "docs" / "link.py").exists()


def test_too_many_files_is_rejected(tmp_path: Path) -> None:
    entries = {f"file{index}.py": b"x" for index in range(5)}
    archive = _write(tmp_path, build_zip(entries))

    with pytest.raises(ArchiveTooLargeError):
        extract_zip(archive, tmp_path / "out", replace(LIMITS, max_files=4))


def test_a_large_individual_file_extracts_and_is_skipped_at_discovery(tmp_path: Path) -> None:
    archive = _write(tmp_path, build_zip({"big.py": b"a" * 2048}))
    destination = tmp_path / "out"

    extract_zip(archive, destination, replace(LIMITS, max_file_bytes=1024))

    assert (destination / "big.py").exists()
    assert discover_files(destination, 1024)[0].skip_reason is SkipReason.TOO_LARGE


def test_a_member_that_understates_its_size_fails_safely(tmp_path: Path) -> None:
    """A member that decompresses past its declared size never lands on disk.

    The declared total is checked before extraction, so a bomb has to lie about
    its size to get that far; the read then fails on the size and CRC mismatch
    and the whole archive is rejected.
    """
    archive = _write(tmp_path, build_understated_zip("bomb.py", b"a" * 100_000))
    destination = tmp_path / "out"

    with zipfile.ZipFile(archive) as opened:
        assert opened.infolist()[0].file_size == 1

    with pytest.raises(MalformedArchiveError):
        extract_zip(archive, destination, replace(LIMITS, max_extracted_bytes=1024))

    assert not (destination / "bomb.py").exists() or (destination / "bomb.py").stat().st_size == 0


def test_oversized_total_extracted_content_is_rejected(tmp_path: Path) -> None:
    entries = {f"file{index}.py": b"a" * 1024 for index in range(4)}
    archive = _write(tmp_path, build_zip(entries))

    with pytest.raises(ArchiveTooLargeError):
        extract_zip(
            archive,
            tmp_path / "out",
            replace(LIMITS, max_extracted_bytes=2048, max_file_bytes=4096),
        )


def test_a_malformed_archive_is_rejected(tmp_path: Path) -> None:
    archive = _write(tmp_path, b"this is not a zip file")

    with pytest.raises(MalformedArchiveError):
        extract_zip(archive, tmp_path / "out", LIMITS)


def test_a_truncated_archive_is_rejected(tmp_path: Path) -> None:
    payload = build_zip({"src/keys.py": b"x = 1\n"})
    archive = _write(tmp_path, payload[: len(payload) // 2])

    with pytest.raises(MalformedArchiveError):
        extract_zip(archive, tmp_path / "out", LIMITS)


def test_an_archive_with_mixed_top_levels_keeps_its_paths(tmp_path: Path) -> None:
    archive = _write(tmp_path, build_raw_zip(["a/one.py", "b/two.py"]))
    destination = tmp_path / "out"

    extract_zip(archive, destination, LIMITS)

    assert (destination / "a" / "one.py").exists()
    assert (destination / "b" / "two.py").exists()
