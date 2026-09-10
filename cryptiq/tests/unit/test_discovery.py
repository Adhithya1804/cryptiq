"""File discovery classifies every file and accounts for every skip."""

from pathlib import Path

from app.engine.discovery import SkipReason, discover_files
from tests.support import write_tree

MAX_FILE_BYTES = 1024


def _by_path(files: list, path: str):
    return next(file for file in files if file.path == path)


def test_every_kind_of_file_is_classified(tmp_path: Path) -> None:
    write_tree(
        tmp_path,
        {
            "src/keys.py": b"x = 1\n",
            "README.md": b"# hi\n",
            "assets/logo.png": b"\x89PNG\x00\x00binary",
            "src/compiled.py": b"\x00\x01\x02binary python",
            "src/huge.py": b"a" * 2048,
            "src/latin.py": "x = 'é'\n".encode("latin-1"),
            ".git/config": b"[core]\n",
            ".git/objects/ab/cdef.py": b"x = 1\n",
        },
    )

    files = discover_files(tmp_path, MAX_FILE_BYTES)

    assert len(files) == 8
    assert _by_path(files, "src/keys.py").is_supported
    assert _by_path(files, "src/keys.py").language == "python"
    assert _by_path(files, "src/keys.py").size == 6
    assert _by_path(files, "README.md").skip_reason is SkipReason.UNSUPPORTED_LANGUAGE
    assert _by_path(files, "assets/logo.png").skip_reason is SkipReason.UNSUPPORTED_LANGUAGE
    assert _by_path(files, "src/compiled.py").skip_reason is SkipReason.BINARY_FILE
    assert _by_path(files, "src/compiled.py").is_binary
    assert _by_path(files, "src/huge.py").skip_reason is SkipReason.TOO_LARGE
    assert _by_path(files, "src/latin.py").skip_reason is SkipReason.INVALID_ENCODING
    assert _by_path(files, ".git/config").skip_reason is SkipReason.IGNORED_PATH
    assert _by_path(files, ".git/objects/ab/cdef.py").skip_reason is SkipReason.IGNORED_PATH


def test_no_file_is_discarded_without_a_reason(tmp_path: Path) -> None:
    write_tree(tmp_path, {"a.py": b"x = 1\n", "b.txt": b"text", ".git/HEAD": b"ref"})

    files = discover_files(tmp_path, MAX_FILE_BYTES)

    assert all(file.is_supported != (file.skip_reason is not None) for file in files)


def test_directories_named_like_build_output_are_still_scanned(tmp_path: Path) -> None:
    write_tree(tmp_path, {"build/generated.py": b"x = 1\n", "venv/lib/thing.py": b"y = 2\n"})

    files = discover_files(tmp_path, MAX_FILE_BYTES)

    assert all(file.is_supported for file in files)


def test_a_file_at_the_size_limit_is_supported(tmp_path: Path) -> None:
    write_tree(tmp_path, {"edge.py": b"a" * MAX_FILE_BYTES})

    files = discover_files(tmp_path, MAX_FILE_BYTES)

    assert files[0].is_supported


def test_the_size_limit_is_the_supplied_ceiling(tmp_path: Path) -> None:
    write_tree(tmp_path, {"edge.py": b"a" * 200})

    files = discover_files(tmp_path, 100)

    assert files[0].skip_reason is SkipReason.TOO_LARGE


def test_symlinks_are_not_followed(tmp_path: Path) -> None:
    write_tree(tmp_path, {"real.py": b"x = 1\n"})
    (tmp_path / "link.py").symlink_to(tmp_path / "real.py")

    files = discover_files(tmp_path, MAX_FILE_BYTES)

    assert [file.path for file in files] == ["real.py"]
