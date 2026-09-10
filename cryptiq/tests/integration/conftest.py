"""Fixtures for the HTTP API integration tests.

The API tests exercise the real routers and services against the in-memory
schema, with the source provider replaced by a fake that serves a tree from
memory. No network, no real worker loop -- ``run_next_job`` is driven
explicitly so a test can assert each lifecycle state.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.dependencies import get_db
from app.engine.ingestion import IngestionLimits, RepositoryReference
from app.engine.ingestion.service import build_result
from app.engine.ingestion.source import SourceSnapshot
from app.main import create_app
from tests.support import write_tree

DEMO_COMMIT = "1f903f5ed2e5e316f345a927555e48535829d8de"
DEMO_URL = "https://github.com/pyca/cryptography"

DEMO_TREE: dict[str, bytes] = {
    "src/signing.py": (
        b"from cryptography.hazmat.primitives.asymmetric import rsa\n"
        b"\n"
        b"class Signer:\n"
        b"    def sign(self, key: rsa.RSAPrivateKey, payload):\n"
        b"        return key.sign(payload)\n"
    ),
    "src/hashing.py": (
        b"from cryptography.hazmat.primitives import hashes\n"
        b"digest = hashes.SHA1()\n"
    ),
}

_LIMITS = IngestionLimits(
    max_archive_bytes=1024 * 1024,
    max_extracted_bytes=1024 * 1024,
    max_files=100,
    max_file_bytes=8192,
)


class FakeSourceProvider:
    """Serves a fixed in-memory tree as a verified snapshot."""

    def __init__(self, tree: dict[str, bytes], commit_sha: str, tmp_root: Path) -> None:
        self._tree = tree
        self._commit_sha = commit_sha
        self._tmp_root = tmp_root

    async def fetch_commit(
        self, repository: RepositoryReference, commit_sha: str
    ) -> SourceSnapshot:
        root = write_tree(self._tmp_root / "snapshot", self._tree)
        return SourceSnapshot(
            root_path=root,
            repository=repository,
            commit_sha=self._commit_sha,
            content_hash="0" * 64,
            file_count=len(self._tree),
        )


class BrokenSourceProvider:
    """Fails ingestion the way a missing commit would."""

    async def fetch_commit(
        self, repository: RepositoryReference, commit_sha: str
    ) -> SourceSnapshot:
        from app.errors import CommitNotFoundError

        raise CommitNotFoundError("The requested commit does not exist.")


@pytest.fixture
def api_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


@pytest.fixture
def api_client(
    api_session_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[TestClient]:
    from app.config import get_settings

    # The API tests drive the worker explicitly via ``run_job``; the
    # background loop must not also run against the real database.
    monkeypatch.setenv("RUN_WORKER", "false")
    get_settings.cache_clear()
    app = create_app()

    def _override_get_db() -> Iterator[Session]:
        db = api_session_factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()
    get_settings.cache_clear()


@pytest.fixture
def fake_provider(tmp_path: Path) -> FakeSourceProvider:
    return FakeSourceProvider(DEMO_TREE, DEMO_COMMIT, tmp_path)


@pytest.fixture
def run_job(
    monkeypatch: pytest.MonkeyPatch,
    api_session_factory: sessionmaker[Session],
    fake_provider: FakeSourceProvider,
):
    """Return an async callable that runs one worker iteration in-process."""
    from app import worker

    monkeypatch.setattr(worker, "SessionLocal", api_session_factory)
    monkeypatch.setattr(worker, "GitHubSourceProvider", lambda: fake_provider)

    async def _run() -> bool:
        return await worker.run_next_job()

    return _run


@pytest.fixture
def analysis_result():
    """A real engine result for the demo tree, for persistence-level tests."""
    from app.engine.pipeline import analyze_snapshot

    def _build(tmp_path: Path):
        root = write_tree(tmp_path / "snapshot", DEMO_TREE)
        snapshot = SourceSnapshot(
            root_path=root,
            repository=RepositoryReference(
                provider="github",
                owner="pyca",
                name="cryptography",
                canonical_url=DEMO_URL,
            ),
            commit_sha=DEMO_COMMIT,
            content_hash="0" * 64,
            file_count=len(DEMO_TREE),
        )
        return analyze_snapshot(build_result(snapshot, _LIMITS), root)

    return _build
