"""Security properties of the standalone CLI.

The CLI is a static-analysis tool. It must never execute code from the target
repository, never follow a symlink out of the tree, never break out of the
snapshot root, and must honour the ingestion resource limits.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from app.cli.main import main

RSA_SOURCE = """\
from cryptography.hazmat.primitives.asymmetric import rsa

k = rsa.generate_private_key(public_exponent=65537, key_size=2048)
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


def test_target_setup_py_is_never_executed(tmp_path: Path, capsys) -> None:
    """A hostile setup.py / conftest.py must not run during a scan."""
    root = _init(tmp_path / "hostile")
    marker = tmp_path / "PWNED"
    payload = f"import pathlib; pathlib.Path({str(marker)!r}).write_text('x')\n"
    (root / "setup.py").write_text(payload)
    (root / "conftest.py").write_text(payload)
    (root / "src.py").write_text(RSA_SOURCE)
    commit = _commit(root, "hostile")

    code, _out, _err = _run(
        ["scan", str(root), "--commit", commit, "--fail-on", "never"], capsys
    )
    assert code == 0
    assert not marker.exists(), "target repository code was executed"

    # working-tree mode too
    _run(["scan", str(root), "--fail-on", "never"], capsys)
    assert not marker.exists()


def test_symlink_escaping_tree_is_not_followed(tmp_path: Path, capsys) -> None:
    secret = tmp_path / "secret.py"
    secret.write_text("API_KEY = 'super-secret'\n")
    root = _init(tmp_path / "repo")
    (root / "real.py").write_text(RSA_SOURCE)
    (root / "link.py").symlink_to(secret)
    commit = _commit(root, "with symlink")

    code, out, _ = _run(
        ["scan", str(root), "--commit", commit, "--json", "--fail-on", "never"], capsys
    )
    assert code == 0
    payload = json.loads(out)
    blob = json.dumps(payload)
    assert "super-secret" not in blob
    files = {f["observed"]["file"] for f in payload["findings"]}
    assert "link.py" not in files


def test_worktree_symlink_is_not_followed(tmp_path: Path, capsys) -> None:
    secret = tmp_path / "secret.py"
    secret.write_text("TOKEN = 'leak-me'\n")
    root = tmp_path / "plain"
    root.mkdir()
    (root / "real.py").write_text(RSA_SOURCE)
    (root / "link.py").symlink_to(secret)

    code, out, _ = _run(["scan", str(root), "--json", "--fail-on", "never"], capsys)
    assert code == 0
    assert "leak-me" not in out


def test_file_count_limit_is_enforced(tmp_path: Path, capsys, monkeypatch) -> None:
    from app.cli import local

    root = tmp_path / "big"
    (root / "pkg").mkdir(parents=True)
    for i in range(12):
        (root / "pkg" / f"m{i}.py").write_text("x = 1\n")

    real = local.IngestionLimits.from_settings

    def _tiny(*_a, **_k):
        limits = real()
        return local.IngestionLimits(
            max_archive_bytes=limits.max_archive_bytes,
            max_extracted_bytes=limits.max_extracted_bytes,
            max_files=5,
            max_file_bytes=limits.max_file_bytes,
        )

    monkeypatch.setattr(local.IngestionLimits, "from_settings", staticmethod(_tiny))
    code, _out, err = _run(["scan", str(root)], capsys)
    assert code == 3
    assert "limit" in err.lower()


def test_no_secrets_in_output(tmp_path: Path, capsys, monkeypatch) -> None:
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_secrettoken123")
    monkeypatch.setenv("GEMINI_API_KEY", "gemini-secret-key")
    root = tmp_path / "r"
    root.mkdir()
    (root / "a.py").write_text(RSA_SOURCE)
    code, out, err = _run(["scan", str(root), "--json", "--fail-on", "never"], capsys)
    assert code == 0
    assert "ghp_secrettoken123" not in out + err
    assert "gemini-secret-key" not in out + err


def test_scan_does_not_reach_network(tmp_path: Path, capsys, monkeypatch) -> None:
    import socket

    def _blocked(*_a, **_k):  # pragma: no cover - only fires on a regression
        raise AssertionError("local scan attempted a network connection")

    monkeypatch.setattr(socket.socket, "connect", _blocked)
    root = tmp_path / "r"
    root.mkdir()
    (root / "a.py").write_text(RSA_SOURCE)
    code, _out, _err = _run(["scan", str(root), "--fail-on", "never"], capsys)
    assert code == 0
