"""Running the RSA rule across a whole parsed snapshot."""

from pathlib import Path

from app.engine.discovery import discover_files
from app.engine.parser import parse_all
from app.engine.rules import evaluate_files
from tests.support import write_tree

MAX_FILE_BYTES = 4096

IMPORT = b"from cryptography.hazmat.primitives.asymmetric import rsa\n"

TREE = {
    "src/b_keys.py": IMPORT + b"key = rsa.generate_private_key()\n",
    "src/a_keys.py": IMPORT
    + b"def sign(payload):\n"
    + b"    key = rsa.generate_private_key()\n"
    + b"    return key.sign(payload)\n",
    "src/broken.py": b"def broken(:\n",
    "src/unrelated.py": b"def run(thing):\n    return thing.sign(b'x')\n",
    "README.md": b"# rsa.generate_private_key\n",
}


def _matches(root: Path):
    parsed = parse_all(root, discover_files(root, MAX_FILE_BYTES))
    return evaluate_files(parsed)


def test_matches_are_collected_across_files_in_a_stable_order(tmp_path: Path) -> None:
    found = _matches(write_tree(tmp_path, TREE))

    assert [(match.file_path, match.location.start_line, match.api) for match in found] == [
        ("src/a_keys.py", 3, "rsa.generate_private_key"),
        ("src/a_keys.py", 4, "RSAPrivateKey.sign"),
        ("src/b_keys.py", 2, "rsa.generate_private_key"),
    ]


def test_a_broken_file_and_unrelated_code_contribute_nothing(tmp_path: Path) -> None:
    found = _matches(write_tree(tmp_path, TREE))

    assert not any(match.file_path in {"src/broken.py", "src/unrelated.py"} for match in found)


def test_the_same_tree_produces_the_same_result_twice(tmp_path: Path) -> None:
    first = _matches(write_tree(tmp_path / "one", TREE))
    second = _matches(write_tree(tmp_path / "two", TREE))

    assert first == second
