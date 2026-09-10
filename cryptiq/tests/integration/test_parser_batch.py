"""Batch parsing over a discovered snapshot."""

from pathlib import Path

import pytest

from app.engine.discovery import DiscoveredFile, discover_files
from app.engine.parser import ParseErrorType, parse_all, parse_sources
from tests.support import write_tree

MAX_FILE_BYTES = 1024

TREE = {
    "src/signing.py": b"from a.b import rsa\n\ndef sign(key):\n    return key.sign(b'x')\n",
    "src/broken.py": b"def broken(:\n",
    "src/nested/util.py": b"class Helper:\n    def run(self):\n        return compute()\n",
    "README.md": b"# not python\n",
    ".git/hooks/pre-commit.py": b"import os\n",
}


def _discovered(root: Path):
    return discover_files(root, MAX_FILE_BYTES)


def test_only_supported_files_are_parsed(tmp_path: Path) -> None:
    root = write_tree(tmp_path, TREE)

    results = parse_all(root, _discovered(root))

    assert [file.path for file in results] == [
        "src/broken.py",
        "src/nested/util.py",
        "src/signing.py",
    ]


def test_one_broken_file_does_not_stop_the_batch(tmp_path: Path) -> None:
    root = write_tree(tmp_path, TREE)

    results = parse_all(root, _discovered(root))
    by_path = {file.path: file for file in results}

    assert by_path["src/broken.py"].error.error_type is ParseErrorType.SYNTAX_ERROR
    assert by_path["src/signing.py"].parsed
    assert by_path["src/nested/util.py"].parsed


def test_the_parsed_files_carry_relative_posix_paths_and_module_paths(tmp_path: Path) -> None:
    root = write_tree(tmp_path, TREE)

    by_path = {file.path: file for file in parse_all(root, _discovered(root))}

    assert by_path["src/nested/util.py"].module_path == "src.nested.util"
    assert not any(file.path.startswith("/") for file in by_path.values())


def test_the_batch_result_does_not_depend_on_input_order(tmp_path: Path) -> None:
    root = write_tree(tmp_path, TREE)
    discovered = _discovered(root)

    forwards = parse_all(root, discovered)
    backwards = parse_all(root, list(reversed(discovered)))

    assert [file.path for file in forwards] == [file.path for file in backwards]
    assert [file.calls for file in forwards] == [file.calls for file in backwards]


def test_a_file_that_vanished_becomes_a_read_error(tmp_path: Path) -> None:
    root = write_tree(tmp_path, TREE)
    discovered = _discovered(root)
    (root / "src" / "signing.py").unlink()

    by_path = {file.path: file for file in parse_all(root, discovered)}

    assert by_path["src/signing.py"].error.error_type is ParseErrorType.READ_ERROR
    assert by_path["src/nested/util.py"].parsed


def test_a_path_escaping_the_root_is_refused(tmp_path: Path) -> None:
    root = write_tree(tmp_path / "snapshot", {"a.py": b"x = 1\n"})
    (tmp_path / "outside.py").write_bytes(b"secret = 1\n")
    escaping = [
        DiscoveredFile(
            path="../outside.py",
            language="python",
            size=11,
            is_binary=False,
            is_supported=True,
            skip_reason=None,
        )
    ]

    results = parse_all(root, escaping)

    assert results[0].error.error_type is ParseErrorType.READ_ERROR


def test_parse_sources_is_ordered_by_path() -> None:
    results = parse_sources([("z.py", "a = 1\n"), ("a.py", "b = 2\n")])

    assert [file.path for file in results] == ["a.py", "z.py"]


def test_parse_sources_rejects_an_unknown_language() -> None:
    with pytest.raises(ValueError):
        parse_sources([("a.rs", "fn main() {}")], language="rust")
