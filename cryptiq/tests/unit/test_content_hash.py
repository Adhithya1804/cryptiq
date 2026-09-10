"""The content hash depends on the source content and nothing else."""

from pathlib import Path

from app.engine.ingestion.source import compute_content_hash, count_files
from tests.support import write_tree

TREE = {
    "src/keys.py": b"x = 1\n",
    "src/nested/other.py": b"y = 2\n",
    "README.md": b"# hi\n",
}


def test_the_same_content_hashes_the_same_in_different_directories(tmp_path: Path) -> None:
    first = write_tree(tmp_path / "first", TREE)
    second = write_tree(tmp_path / "second", TREE)

    assert compute_content_hash(first) == compute_content_hash(second)


def test_changing_a_file_changes_the_hash(tmp_path: Path) -> None:
    first = write_tree(tmp_path / "first", TREE)
    second = write_tree(tmp_path / "second", {**TREE, "src/keys.py": b"x = 2\n"})

    assert compute_content_hash(first) != compute_content_hash(second)


def test_renaming_a_file_changes_the_hash(tmp_path: Path) -> None:
    first = write_tree(tmp_path / "first", {"a.py": b"x = 1\n"})
    second = write_tree(tmp_path / "second", {"b.py": b"x = 1\n"})

    assert compute_content_hash(first) != compute_content_hash(second)


def test_adding_a_file_changes_the_hash(tmp_path: Path) -> None:
    first = write_tree(tmp_path / "first", TREE)
    second = write_tree(tmp_path / "second", {**TREE, "extra.py": b"z = 3\n"})

    assert compute_content_hash(first) != compute_content_hash(second)


def test_the_hash_is_a_sha256_hex_digest(tmp_path: Path) -> None:
    digest = compute_content_hash(write_tree(tmp_path, TREE))

    assert len(digest) == 64
    assert int(digest, 16) >= 0


def test_an_empty_tree_hashes_deterministically(tmp_path: Path) -> None:
    empty = tmp_path / "empty"
    empty.mkdir()

    assert compute_content_hash(empty) == compute_content_hash(empty)
    assert count_files(empty) == 0


def test_count_files_counts_regular_files_only(tmp_path: Path) -> None:
    root = write_tree(tmp_path, TREE)
    (root / "link.py").symlink_to(root / "src" / "keys.py")

    assert count_files(root) == 3
