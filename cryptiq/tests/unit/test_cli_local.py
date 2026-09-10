"""Local-mode CLI tests: ``cryptiq scan <path>`` and ``cryptiq version``.

These run the real deterministic engine in-process over throwaway trees and
Git repositories built in ``tmp_path``. No network, no database, no backend.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from app.cli.main import main

RSA_SOURCE = """\
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import hashes


def make_key():
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def digest(data):
    return hashes.Hash(hashes.SHA256())
"""

X25519_SOURCE = """\
from cryptography.hazmat.primitives.asymmetric import x25519


def new_key():
    return x25519.X25519PrivateKey.generate()
"""


def _run(argv: list[str], capsys) -> tuple[int, str, str]:
    code = main(argv)
    captured = capsys.readouterr()
    return code, captured.out, captured.err


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


def _init_repo(root: Path) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    _git(root, "init", "-q")
    _git(root, "config", "user.email", "t@example.com")
    _git(root, "config", "user.name", "Tester")
    return root


def _commit_all(repo: Path, message: str) -> str:
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", message)
    return _git(repo, "rev-parse", "HEAD")


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    root = _init_repo(tmp_path / "sample")
    (root / "src").mkdir()
    (root / "src" / "signing.py").write_text(RSA_SOURCE)
    _commit_all(root, "initial")
    return root


# --------------------------------------------------------------------------- #
# version
# --------------------------------------------------------------------------- #


def test_version_text(capsys) -> None:
    code, out, _ = _run(["version"], capsys)
    assert code == 0
    assert "cryptiq" in out
    assert "ruleset_version" in out


def test_version_json(capsys) -> None:
    code, out, _ = _run(["version", "--json"], capsys)
    assert code == 0
    payload = json.loads(out)
    assert payload["engine"]["parser_version"]
    assert payload["engine"]["ruleset_version"]
    assert payload["engine"]["pqc_ruleset_version"]


# --------------------------------------------------------------------------- #
# scan -- worktree
# --------------------------------------------------------------------------- #


def test_scan_worktree_text_reports_findings(repo: Path, capsys) -> None:
    code, out, _ = _run(["scan", str(repo)], capsys)
    assert code == 1  # a HIGH finding is present, default --fail-on high
    assert "CRYPTIQ SCAN" in out
    assert "RSA" in out
    assert "KEY_GENERATION" in out


def test_scan_fail_on_never_exits_zero(repo: Path, capsys) -> None:
    code, _out, _ = _run(["scan", str(repo), "--fail-on", "never"], capsys)
    assert code == 0


def test_scan_json_is_grouped_and_machine_readable(repo: Path, capsys) -> None:
    code, out, _ = _run(["scan", str(repo), "--json", "--fail-on", "never"], capsys)
    assert code == 0
    payload = json.loads(out)
    assert payload["mode"] == "worktree"
    assert payload["findings"]
    first = payload["findings"][0]
    for block in ("observed", "inference", "migration_review", "impact", "priority", "review"):
        assert block in first
    # local scans have no persisted review lifecycle
    assert first["review"]["status"] is None
    assert first["id"] is None
    assert first["fingerprint"]


def test_scan_repeated_is_byte_identical(repo: Path, capsys) -> None:
    code_a, out_a, _ = _run(["scan", str(repo), "--json", "--fail-on", "never"], capsys)
    code_b, out_b, _ = _run(["scan", str(repo), "--json", "--fail-on", "never"], capsys)
    assert code_a == code_b == 0
    a = json.loads(out_a)
    b = json.loads(out_b)
    assert a["findings"] == b["findings"]


def test_scan_missing_path_is_usage_error(tmp_path: Path, capsys) -> None:
    code, _out, err = _run(["scan", str(tmp_path / "nope")], capsys)
    assert code == 2
    assert "does not exist" in err


def test_scan_file_target_is_usage_error(tmp_path: Path, capsys) -> None:
    target = tmp_path / "a.py"
    target.write_text("x = 1\n")
    code, _out, err = _run(["scan", str(target)], capsys)
    assert code == 2
    assert "directory" in err


def test_scan_empty_repository_has_no_findings(tmp_path: Path, capsys) -> None:
    root = _init_repo(tmp_path / "empty")
    (root / "README.md").write_text("# empty\n")
    _commit_all(root, "empty")
    code, out, _ = _run(["scan", str(root), "--json"], capsys)
    assert code == 0
    assert json.loads(out)["findings"] == []


def test_scan_non_git_directory_still_works(tmp_path: Path, capsys) -> None:
    plain = tmp_path / "plain"
    (plain / "pkg").mkdir(parents=True)
    (plain / "pkg" / "a.py").write_text(RSA_SOURCE)
    code, out, _ = _run(["scan", str(plain), "--json", "--fail-on", "never"], capsys)
    assert code == 0
    payload = json.loads(out)
    assert payload["commit_sha"] is None
    assert payload["findings"]


def test_scan_worktree_skips_vendored_dirs_by_default(repo: Path, capsys) -> None:
    vendored = repo / ".venv" / "lib"
    vendored.mkdir(parents=True)
    (vendored / "evil.py").write_text(RSA_SOURCE)
    _code, out, _ = _run(["scan", str(repo), "--json", "--fail-on", "never"], capsys)
    payload = json.loads(out)
    files = {f["observed"]["file"] for f in payload["findings"]}
    assert not any(".venv" in path for path in files)

    _code, out, _ = _run(
        ["scan", str(repo), "--json", "--fail-on", "never", "--include-all"], capsys
    )
    payload = json.loads(out)
    files = {f["observed"]["file"] for f in payload["findings"]}
    assert any(".venv" in path for path in files)


# --------------------------------------------------------------------------- #
# scan -- specific commit
# --------------------------------------------------------------------------- #


def test_scan_commit_uses_archive_not_worktree(repo: Path, capsys) -> None:
    base = _git(repo, "rev-parse", "HEAD")
    # Add an uncommitted file that would change results if the worktree were read.
    (repo / "src" / "uncommitted.py").write_text(X25519_SOURCE)

    code, out, _ = _run(
        ["scan", str(repo), "--commit", base, "--json", "--fail-on", "never"], capsys
    )
    assert code == 0
    payload = json.loads(out)
    assert payload["mode"] == "commit"
    assert payload["commit_sha"] == base
    files = {f["observed"]["file"] for f in payload["findings"]}
    assert "src/uncommitted.py" not in files


def test_scan_commit_short_sha_resolves(repo: Path, capsys) -> None:
    full = _git(repo, "rev-parse", "HEAD")
    code, out, _ = _run(
        ["scan", str(repo), "--commit", full[:8], "--json", "--fail-on", "never"], capsys
    )
    assert code == 0
    assert json.loads(out)["commit_sha"] == full


def test_scan_commit_unknown_is_usage_error(repo: Path, capsys) -> None:
    code, _out, err = _run(["scan", str(repo), "--commit", "deadbeef"], capsys)
    assert code == 2
    assert "resolve commit" in err


def test_scan_commit_needs_git_repo(tmp_path: Path, capsys) -> None:
    plain = tmp_path / "plain"
    plain.mkdir()
    (plain / "a.py").write_text("x = 1\n")
    code, _out, err = _run(["scan", str(plain), "--commit", "HEAD"], capsys)
    assert code == 2
    assert "Git repository" in err


# --------------------------------------------------------------------------- #
# SARIF
# --------------------------------------------------------------------------- #


def test_scan_sarif_is_valid_211(repo: Path, capsys) -> None:
    code, out, _ = _run(["scan", str(repo), "--format", "sarif", "--fail-on", "never"], capsys)
    assert code == 0
    doc = json.loads(out)
    assert doc["version"] == "2.1.0"
    run = doc["runs"][0]
    assert run["tool"]["driver"]["name"] == "Cryptiq"
    assert run["tool"]["driver"]["rules"]
    result = run["results"][0]
    uri = result["locations"][0]["physicalLocation"]["artifactLocation"]["uri"]
    assert not uri.startswith("/")  # repository-relative, never absolute
    assert "cryptiqFingerprint/v1" in result["partialFingerprints"]


def test_scan_sarif_shorthand_matches_format_sarif(repo: Path, capsys) -> None:
    code_a, out_a, _ = _run(["scan", str(repo), "--sarif", "--fail-on", "never"], capsys)
    code_b, out_b, _ = _run(
        ["scan", str(repo), "--format", "sarif", "--fail-on", "never"], capsys
    )
    assert code_a == 0 and code_b == 0
    assert json.loads(out_a) == json.loads(out_b)
    assert json.loads(out_a)["version"] == "2.1.0"


def test_scan_invalid_format_is_usage_error(repo: Path, capsys) -> None:
    with pytest.raises(SystemExit) as exc:
        _run(["scan", str(repo), "--format", "xml"], capsys)
    assert exc.value.code == 2
