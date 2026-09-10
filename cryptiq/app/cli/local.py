"""Local analysis: run the deterministic engine in-process, offline.

This is the standalone half of the CLI. It reuses the *same* engine the
FastAPI worker runs -- ``app.engine.pipeline.analyze_snapshot`` -- over a
snapshot it builds from a local directory or a local Git commit. There is no
second analysis implementation here: parsing, rules, role inference, PQC
mapping, impact, priority and fingerprints all come from ``app.engine``.

What this module owns is narrow:

* turning a path (and optionally a commit) into a
  :class:`~app.engine.ingestion.source.SourceSnapshot` without a network,
* a Git ``archive`` extraction that never runs a repository hook or build,
* the resource limits (file count, size) applied to a local tree.

Nothing in local mode contacts GitHub, a database, Redis, Celery, Docker or
Gemini. The only subprocess ever spawned is ``git`` itself, and only to read
objects (``rev-parse``, ``archive``, ``remote get-url``, ``status``); no
command from the target repository is executed.
"""

from __future__ import annotations

import hashlib
import logging
import shutil
import subprocess
import tarfile
import tempfile
from collections import Counter
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from urllib.parse import urlsplit

from app.cli.client import EXIT_SCAN_FAILED, EXIT_USAGE, CliError
from app.engine.discovery import DiscoveredFile, discover_files
from app.engine.ingestion import (
    IngestionLimits,
    IngestionResult,
    RepositoryReference,
    SourceSnapshot,
)
from app.engine.pipeline import AnalysisResult, analyze_snapshot
from app.errors import InvalidRepositoryUrlError
from app.integrations.github import parse_repository_url

logger = logging.getLogger(__name__)

#: Directories a local *working-tree* scan skips by default. These hold
#: dependencies, virtual environments and tool caches -- never the source the
#: user wrote -- and walking them would be slow and noisy. ``--include-all``
#: turns the filter off for exact engine parity. A ``--commit`` scan never
#: needs this: ``git archive`` only ever contains tracked files.
DEFAULT_EXCLUDED_DIRS = frozenset(
    {
        ".git",
        ".hg",
        ".svn",
        ".bzr",
        "node_modules",
        ".venv",
        "venv",
        "env",
        ".env",
        "virtualenv",
        "site-packages",
        ".tox",
        ".nox",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        ".hypothesis",
        "__pycache__",
        ".eggs",
        ".idea",
        ".vscode",
    }
)

_GIT = "git"
_GIT_TIMEOUT = 60
_ARCHIVE_TIMEOUT = 300
_CONTENT_HASH_ALGORITHM = "sha256"


# --------------------------------------------------------------------------- #
# metadata returned alongside a local analysis
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class LocalScanMeta:
    """Context about how a local analysis was produced, for the summary line."""

    target: str
    mode: str  # "worktree" | "commit"
    commit_sha: str | None
    repository_label: str
    dirty: bool = False


# --------------------------------------------------------------------------- #
# git helpers -- read-only, no shell, no repository code
# --------------------------------------------------------------------------- #


def _git(repo: Path, *args: str, timeout: int = _GIT_TIMEOUT) -> subprocess.CompletedProcess[str]:
    """Run one read-only ``git`` command in ``repo``. Never uses a shell.

    If ``git`` is not installed, a non-zero result is returned rather than
    raising, so working-tree detection simply falls back to "not a Git repo".
    """
    try:
        return subprocess.run(
            [_GIT, "-C", str(repo), *args],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except FileNotFoundError:
        return subprocess.CompletedProcess(args=[_GIT, *args], returncode=127, stdout="", stderr="git not found")


def is_git_repository(path: Path) -> bool:
    """True when ``path`` is inside a Git working tree."""
    result = _git(path, "rev-parse", "--is-inside-work-tree")
    return result.returncode == 0 and result.stdout.strip() == "true"


def repository_root(path: Path) -> Path:
    """Return the Git top-level directory for ``path`` (or ``path`` itself)."""
    result = _git(path, "rev-parse", "--show-toplevel")
    if result.returncode == 0 and result.stdout.strip():
        return Path(result.stdout.strip())
    return path


def resolve_commit(repo: Path, rev: str) -> str:
    """Resolve a revision to a full 40-character commit SHA, locally.

    ``rev`` is passed to ``git rev-parse`` as a single argument -- it is never
    interpolated into a shell -- and must name a commit that already exists in
    the local object store. Nothing is fetched.
    """
    result = _git(repo, "rev-parse", "--verify", "--quiet", f"{rev}^{{commit}}")
    sha = result.stdout.strip()
    if result.returncode != 0 or len(sha) != 40:
        raise CliError(
            f"Could not resolve commit {rev!r} in {repo}. "
            "It must be a commit that already exists locally "
            "(fetch it first if it is remote-only).",
            exit_code=EXIT_USAGE,
        )
    return sha.lower()


def head_commit(repo: Path) -> str | None:
    """Return the current HEAD SHA, or ``None`` if there is no commit yet."""
    result = _git(repo, "rev-parse", "--verify", "--quiet", "HEAD")
    sha = result.stdout.strip()
    return sha.lower() if result.returncode == 0 and len(sha) == 40 else None


def working_tree_is_dirty(repo: Path) -> bool:
    """True when the working tree has staged or unstaged changes."""
    result = _git(repo, "status", "--porcelain")
    return result.returncode == 0 and bool(result.stdout.strip())


def _normalise_remote_url(url: str) -> str | None:
    """Turn a Git remote URL into an ``https://github.com/owner/name`` form.

    Handles the three shapes Git emits (``https://``, ``ssh://`` and the
    ``git@host:owner/name`` scp form). Returns ``None`` for anything that is
    not a GitHub remote, so the caller falls back to a local reference.
    """
    candidate = url.strip()
    if not candidate:
        return None
    if candidate.startswith("git@"):
        host, _, path = candidate[4:].partition(":")
        candidate = f"https://{host}/{path}"
    parts = urlsplit(candidate)
    host = (parts.hostname or "").lower()
    if host not in {"github.com", "www.github.com"}:
        return None
    segments = [s for s in parts.path.split("/") if s]
    if len(segments) < 2:
        return None
    owner, name = segments[0], segments[1].removesuffix(".git")
    return f"https://github.com/{owner}/{name}"


def repository_reference_for(path: Path) -> RepositoryReference:
    """Return the repository identity used for fingerprints.

    If the tree has a GitHub ``origin`` remote the reference is the real
    ``github/owner/name`` -- so a local finding and the same finding from the
    hosted API share a fingerprint. Otherwise a stable ``local/<dir>``
    reference is used, which is enough for the CLI's own diffing.
    """
    if is_git_repository(path):
        remote = _git(path, "remote", "get-url", "origin")
        if remote.returncode == 0:
            normalised = _normalise_remote_url(remote.stdout.strip())
            if normalised is not None:
                try:
                    return parse_repository_url(normalised)
                except InvalidRepositoryUrlError:  # pragma: no cover - falls through
                    logger.debug("origin remote %r is not a plain GitHub repo URL", normalised)
    root = repository_root(path)
    name = root.name or "repository"
    return RepositoryReference(
        provider="local",
        owner="local",
        name=name,
        canonical_url=str(root),
    )


# --------------------------------------------------------------------------- #
# snapshot construction
# --------------------------------------------------------------------------- #


def _safe_member_path(name: str) -> PurePosixPath | None:
    """Return a member's path if it stays inside the root, else ``None``."""
    if not name or name in {".", "./"} or "\\" in name or name.startswith("/"):
        return None
    parts = [p for p in PurePosixPath(name).parts if p not in {".", ""}]
    if any(p == ".." for p in parts) or not parts:
        return None
    return PurePosixPath(*parts)


@contextmanager
def _git_archive_snapshot(repo: Path, full_sha: str, limits: IngestionLimits) -> Iterator[Path]:
    """Extract ``git archive <sha>`` into a temp dir and yield its path.

    ``git archive`` writes a tar of exactly the tracked tree at that commit.
    It runs no hook and no filter, and this extractor writes **regular files
    only** -- symlinks, hardlinks and device entries in the tar are skipped,
    never recreated -- so nothing from the archive can point outside the root
    or be executed. The working tree is never touched.
    """
    workspace = Path(tempfile.mkdtemp(prefix="cryptiq-cli-"))
    proc = subprocess.Popen(
        [_GIT, "-C", str(repo), "archive", "--format=tar", full_sha],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    try:
        assert proc.stdout is not None
        extracted_bytes = 0
        file_count = 0
        with tarfile.open(fileobj=proc.stdout, mode="r|") as tar:
            for member in tar:
                if member.isdir():
                    continue
                if not member.isreg():
                    # symlink / hardlink / device / fifo -- never recreated
                    continue
                relative = _safe_member_path(member.name)
                if relative is None:
                    raise CliError(
                        f"Refusing archive entry {member.name!r}: it escapes the root.",
                        exit_code=EXIT_SCAN_FAILED,
                    )
                file_count += 1
                if file_count > limits.max_files:
                    raise CliError(
                        f"Repository has more than the {limits.max_files} permitted files.",
                        exit_code=EXIT_SCAN_FAILED,
                    )
                extracted_bytes += member.size
                if extracted_bytes > limits.max_extracted_bytes:
                    raise CliError(
                        f"Repository exceeds the {limits.max_extracted_bytes} byte limit.",
                        exit_code=EXIT_SCAN_FAILED,
                    )
                target = workspace / Path(*relative.parts)
                target.parent.mkdir(parents=True, exist_ok=True)
                source = tar.extractfile(member)
                if source is None:  # pragma: no cover - defensive
                    continue
                with target.open("wb") as sink:
                    shutil.copyfileobj(source, sink, length=1024 * 1024)

        _, stderr = proc.communicate(timeout=_ARCHIVE_TIMEOUT)
        if proc.returncode != 0:
            raise CliError(
                f"git archive failed for {full_sha}: {stderr.decode('utf-8', 'replace').strip()}",
                exit_code=EXIT_SCAN_FAILED,
            )
        yield workspace
    finally:
        if proc.poll() is None:  # pragma: no cover - defensive
            proc.kill()
        shutil.rmtree(workspace, ignore_errors=True)


def _hash_supported(root: Path, discovered: list[DiscoveredFile]) -> str:
    """A deterministic content hash over the analysed file set.

    Same convention as ``app.engine.ingestion.source.compute_content_hash``
    (sorted relative path, NUL, file digest, newline) but scoped to the files
    the scan will actually parse, so a working-tree scan does not have to read
    every vendored byte to get a stable identity.
    """
    digest = hashlib.new(_CONTENT_HASH_ALGORITHM)
    for discovered_file in sorted(discovered, key=lambda f: f.path):
        if not discovered_file.is_supported:
            continue
        target = (root / discovered_file.path).resolve()
        if root.resolve() not in target.parents:
            continue
        file_digest = hashlib.new(_CONTENT_HASH_ALGORITHM)
        try:
            with target.open("rb") as handle:
                while chunk := handle.read(1024 * 1024):
                    file_digest.update(chunk)
        except OSError:
            continue
        digest.update(discovered_file.path.encode("utf-8"))
        digest.update(b"\x00")
        digest.update(file_digest.hexdigest().encode("ascii"))
        digest.update(b"\n")
    return digest.hexdigest()


def _excluded(path: str) -> bool:
    return any(part in DEFAULT_EXCLUDED_DIRS for part in PurePosixPath(path).parts)


def _build_ingestion(
    root: Path,
    repository: RepositoryReference,
    commit_sha: str,
    *,
    include_all: bool,
    limits: IngestionLimits,
) -> IngestionResult:
    """Discover the files under ``root`` and wrap them for the pipeline."""
    discovered = discover_files(root, limits.max_file_bytes)
    if not include_all:
        discovered = [f for f in discovered if not _excluded(f.path)]

    if len(discovered) > limits.max_files:
        raise CliError(
            f"Repository has {len(discovered)} files, over the "
            f"{limits.max_files} limit. Narrow the target or raise "
            "CRYPTIQ_MAX_FILES.",
            exit_code=EXIT_SCAN_FAILED,
        )

    analyzed = sum(1 for f in discovered if f.is_supported)
    reasons = Counter(f.skip_reason for f in discovered if f.skip_reason is not None)
    snapshot = SourceSnapshot(
        root_path=root,
        repository=repository,
        commit_sha=commit_sha,
        content_hash=_hash_supported(root, discovered),
        file_count=len(discovered),
    )
    return IngestionResult(
        snapshot=snapshot,
        discovered_files=discovered,
        total_files=len(discovered),
        analyzed_files=analyzed,
        skipped_files=len(discovered) - analyzed,
        skipped_reasons=dict(reasons),
    )


# --------------------------------------------------------------------------- #
# public entry points
# --------------------------------------------------------------------------- #


def resolve_target(raw: str) -> Path:
    """Resolve a user-supplied target path to an existing directory."""
    path = Path(raw).expanduser()
    try:
        resolved = path.resolve()
    except OSError as exc:  # pragma: no cover - defensive
        raise CliError(f"Invalid target path {raw!r}: {exc}", exit_code=EXIT_USAGE) from exc
    if not resolved.exists():
        raise CliError(f"Target path does not exist: {resolved}", exit_code=EXIT_USAGE)
    if not resolved.is_dir():
        raise CliError(
            f"Target must be a directory (got a file): {resolved}", exit_code=EXIT_USAGE
        )
    return resolved


@contextmanager
def local_analysis(
    target: str,
    *,
    commit: str | None = None,
    include_all: bool = False,
    limits: IngestionLimits | None = None,
) -> Iterator[tuple[AnalysisResult, LocalScanMeta]]:
    """Analyse a local target with the deterministic engine.

    Yields ``(AnalysisResult, LocalScanMeta)``. With ``commit`` the analysed
    tree is that commit's ``git archive`` (the working tree is not read or
    modified); without it, the current working tree is analysed in place.
    """
    limits = limits or IngestionLimits.from_settings()
    root = resolve_target(target)
    repository = repository_reference_for(root)
    label = (
        repository.slug
        if repository.provider != "local"
        else f"local:{repository.name}"
    )

    if commit is not None:
        if not is_git_repository(root):
            raise CliError(
                f"--commit needs a Git repository; {root} is not one.",
                exit_code=EXIT_USAGE,
            )
        repo_root = repository_root(root)
        full_sha = resolve_commit(repo_root, commit)
        with _git_archive_snapshot(repo_root, full_sha, limits) as snapshot_root:
            ingestion = _build_ingestion(
                snapshot_root, repository, full_sha, include_all=True, limits=limits
            )
            result = analyze_snapshot(ingestion, snapshot_root)
            yield result, LocalScanMeta(
                target=str(root),
                mode="commit",
                commit_sha=full_sha,
                repository_label=label,
            )
        return

    commit_sha = head_commit(root) if is_git_repository(root) else None
    dirty = working_tree_is_dirty(root) if is_git_repository(root) else False
    ingestion = _build_ingestion(
        root, repository, commit_sha or "WORKING_TREE", include_all=include_all, limits=limits
    )
    result = analyze_snapshot(ingestion, root)
    yield result, LocalScanMeta(
        target=str(root),
        mode="worktree",
        commit_sha=commit_sha,
        repository_label=label,
        dirty=dirty,
    )
