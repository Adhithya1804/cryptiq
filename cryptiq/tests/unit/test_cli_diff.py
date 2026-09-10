"""``cryptiq diff`` tests: fingerprint-based NEW / FIXED / UNCHANGED.

The comparison must use the CRYPTIQ finding fingerprint, not line numbers, so
inserting lines above an unchanged call keeps it UNCHANGED.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from app.cli.main import main

RSA_SOURCE = """\
from cryptography.hazmat.primitives.asymmetric import rsa


def make_key():
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)
"""

X25519_SOURCE = """\
from cryptography.hazmat.primitives.asymmetric import x25519


def new_key():
    return x25519.X25519PrivateKey.generate()
"""


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True, check=True
    ).stdout.strip()


def _init(root: Path) -> Path:
    root.mkdir(parents=True)
    _git(root, "init", "-q")
    _git(root, "config", "user.email", "t@example.com")
    _git(root, "config", "user.name", "Tester")
    return root


def _commit(repo: Path, message: str) -> str:
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", message)
    return _git(repo, "rev-parse", "HEAD")


def _run(argv: list[str], capsys) -> tuple[int, str, str]:
    code = main(argv)
    cap = capsys.readouterr()
    return code, cap.out, cap.err


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    root = _init(tmp_path / "r")
    (root / "a.py").write_text(RSA_SOURCE)
    return root


def test_diff_new_finding(repo: Path, capsys) -> None:
    base = _commit(repo, "base")
    (repo / "b.py").write_text(X25519_SOURCE)
    head = _commit(repo, "add x25519")

    code, out, _ = _run(
        ["diff", "--target", str(repo), "--base", base, "--head", head], capsys
    )
    assert code == 1  # NEW findings -> exit 1
    assert "NEW (1)" in out
    assert "X25519" in out
    assert "FIXED (0)" in out
    assert "UNCHANGED (1)" in out


def test_diff_fixed_finding(repo: Path, capsys) -> None:
    (repo / "b.py").write_text(X25519_SOURCE)
    base = _commit(repo, "base with two")
    (repo / "b.py").unlink()
    head = _commit(repo, "remove x25519")

    code, out, _ = _run(
        ["diff", "--target", str(repo), "--base", base, "--head", head, "--json"], capsys
    )
    assert code == 0
    payload = json.loads(out)
    assert payload["summary"] == {"new": 0, "fixed": 1, "unchanged": 1}
    assert payload["fixed"][0]["observed"]["algorithm"] == "X25519"


def test_diff_line_shift_is_unchanged_not_new(repo: Path, capsys) -> None:
    base = _commit(repo, "base")
    # Prepend comment lines: the call moves down, the fingerprint does not change.
    shifted = "# a comment\n# another\n# and one more\n" + RSA_SOURCE
    (repo / "a.py").write_text(shifted)
    head = _commit(repo, "shift lines")

    code, out, _ = _run(
        ["diff", "--target", str(repo), "--base", base, "--head", head, "--json"], capsys
    )
    assert code == 0
    payload = json.loads(out)
    assert payload["summary"]["new"] == 0
    assert payload["summary"]["fixed"] == 0
    assert payload["summary"]["unchanged"] == 1


def test_diff_no_change_all_unchanged(repo: Path, capsys) -> None:
    base = _commit(repo, "base")
    (repo / "note.txt").write_text("hello\n")
    head = _commit(repo, "docs only")

    code, out, _ = _run(
        ["diff", "--target", str(repo), "--base", base, "--head", head], capsys
    )
    assert code == 0
    assert "NEW (0)" in out
    assert "FIXED (0)" in out


def test_diff_deterministic_ordering(repo: Path, capsys) -> None:
    base = _commit(repo, "base")
    (repo / "b.py").write_text(X25519_SOURCE)
    (repo / "c.py").write_text(RSA_SOURCE.replace("make_key", "make_key_two"))
    head = _commit(repo, "add more")

    outs = []
    for _ in range(2):
        _code, out, _err = _run(
            ["diff", "--target", str(repo), "--base", base, "--head", head, "--json"],
            capsys,
        )
        outs.append(out)
    assert outs[0] == outs[1]
    payload = json.loads(outs[0])
    ranks = [f["priority"]["level"] for f in payload["new"]]
    # highest priority first
    assert ranks == sorted(ranks, key={"HIGH": 0, "MEDIUM": 1, "LOW": 2}.get)


def test_diff_no_fail_on_new_flag(repo: Path, capsys) -> None:
    base = _commit(repo, "base")
    (repo / "b.py").write_text(X25519_SOURCE)
    head = _commit(repo, "add x25519")
    code, _out, _ = _run(
        [
            "diff", "--target", str(repo), "--base", base, "--head", head,
            "--no-fail-on-new",
        ],
        capsys,
    )
    assert code == 0


def test_diff_unknown_commit_is_usage_error(repo: Path, capsys) -> None:
    base = _commit(repo, "base")
    code, _out, err = _run(
        ["diff", "--target", str(repo), "--base", base, "--head", "nope"], capsys
    )
    assert code == 2
    assert "resolve commit" in err
