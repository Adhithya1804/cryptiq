"""The AWS/demo hardening controls, tested end to end through the API.

Three low-complexity protections for the unauthenticated demo endpoint:

* a request body-size ceiling (``413 REQUEST_TOO_LARGE``),
* a bound on scans QUEUED or RUNNING at once (``429 TOO_MANY_SCANS``),
  which frees up as scans complete *or* fail,
* the ability to hide ``/docs`` + ``/openapi.json`` in the demo profile
  without breaking local development.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from app.config import get_settings
from app.dependencies import get_db
from app.main import create_app
from tests.integration.conftest import DEMO_COMMIT, DEMO_URL


def _client(api_session_factory: sessionmaker[Session]) -> Iterator[TestClient]:
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


@pytest.fixture
def hardened_client(
    api_session_factory: sessionmaker[Session], monkeypatch: pytest.MonkeyPatch
) -> Iterator[TestClient]:
    """A client with a tiny body limit, a low in-flight cap and docs hidden."""
    monkeypatch.setenv("RUN_WORKER", "false")
    monkeypatch.setenv("MAX_REQUEST_BODY_BYTES", "2000")
    monkeypatch.setenv("MAX_IN_FLIGHT_SCANS", "3")
    monkeypatch.setenv("EXPOSE_API_DOCS", "false")
    get_settings.cache_clear()
    yield from _client(api_session_factory)
    get_settings.cache_clear()


def _submit(client: TestClient, commit: str):
    return client.post(
        "/api/v1/scans",
        json={"repository_url": DEMO_URL, "commit_sha": commit},
    )


# --------------------------------------------------------------------------- #
# 1. Request body-size limit
# --------------------------------------------------------------------------- #


def test_oversized_body_is_rejected_with_413(hardened_client: TestClient) -> None:
    payload = {"repository_url": DEMO_URL, "commit_sha": DEMO_COMMIT, "pad": "x" * 5000}
    response = hardened_client.post("/api/v1/scans", json=payload)

    assert response.status_code == 413, response.text
    assert response.json()["error"]["code"] == "REQUEST_TOO_LARGE"


def test_normal_scan_request_is_under_the_limit(
    hardened_client: TestClient, run_job
) -> None:
    response = _submit(hardened_client, DEMO_COMMIT)
    assert response.status_code == 202, response.text


# --------------------------------------------------------------------------- #
# 2. In-flight scan cap
# --------------------------------------------------------------------------- #


async def test_in_flight_cap_accepts_up_to_limit_then_429s(
    hardened_client: TestClient,
) -> None:
    commits = [f"{i:040x}" for i in range(1, 4)]
    for commit in commits:
        assert _submit(hardened_client, commit).status_code == 202

    # Fourth distinct scan: three are already QUEUED, limit is 3.
    over = _submit(hardened_client, f"{99:040x}")
    assert over.status_code == 429, over.text
    assert over.json()["error"]["code"] == "TOO_MANY_SCANS"


async def test_completed_scan_releases_capacity(
    api_session_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    from app import worker
    from app.engine.ingestion.source import SourceSnapshot
    from tests.integration.conftest import DEMO_TREE, FakeSourceProvider
    from tests.support import write_tree

    class EchoProvider(FakeSourceProvider):
        """Snapshot stamped with the *requested* commit, so the scan COMPLETEs."""

        async def fetch_commit(self, repository, commit_sha):
            root = write_tree(self._tmp_root / f"snap-{commit_sha[:8]}", DEMO_TREE)
            return SourceSnapshot(
                root_path=root,
                repository=repository,
                commit_sha=commit_sha,
                content_hash="0" * 64,
                file_count=len(DEMO_TREE),
            )

    monkeypatch.setenv("RUN_WORKER", "false")
    monkeypatch.setenv("MAX_IN_FLIGHT_SCANS", "3")
    get_settings.cache_clear()

    provider = EchoProvider(DEMO_TREE, "unused", tmp_path)
    monkeypatch.setattr(worker, "SessionLocal", api_session_factory)
    monkeypatch.setattr(worker, "GitHubSourceProvider", lambda: provider)

    clients = _client(api_session_factory)
    client = next(clients)
    try:
        for commit in (f"{i:040x}" for i in range(1, 4)):
            assert _submit(client, commit).status_code == 202
        assert _submit(client, f"{50:040x}").status_code == 429

        assert await worker.run_next_job() is True  # one QUEUED -> COMPLETED

        assert _submit(client, f"{51:040x}").status_code == 202
    finally:
        next(clients, None)
        get_settings.cache_clear()


async def test_failed_scan_releases_capacity(
    api_session_factory: sessionmaker[Session], monkeypatch: pytest.MonkeyPatch
) -> None:
    from app import worker
    from tests.integration.conftest import BrokenSourceProvider

    monkeypatch.setenv("RUN_WORKER", "false")
    monkeypatch.setenv("MAX_IN_FLIGHT_SCANS", "2")
    get_settings.cache_clear()
    monkeypatch.setattr(worker, "SessionLocal", api_session_factory)
    monkeypatch.setattr(worker, "GitHubSourceProvider", BrokenSourceProvider)

    clients = _client(api_session_factory)
    client = next(clients)
    try:
        assert _submit(client, f"{1:040x}").status_code == 202
        assert _submit(client, f"{2:040x}").status_code == 202
        assert _submit(client, f"{3:040x}").status_code == 429

        # Drive the broken job to FAILED (no retries left after the loop).
        for _ in range(5):
            if not await worker.run_next_job():
                break

        assert _submit(client, f"{4:040x}").status_code == 202
    finally:
        next(clients, None)
        get_settings.cache_clear()


# --------------------------------------------------------------------------- #
# 3. API docs exposure
# --------------------------------------------------------------------------- #


def test_docs_hidden_in_demo_profile(hardened_client: TestClient) -> None:
    assert hardened_client.get("/docs").status_code == 404
    assert hardened_client.get("/openapi.json").status_code == 404


def test_docs_present_by_default(client: TestClient) -> None:
    assert client.get("/docs").status_code == 200
    assert client.get("/openapi.json").status_code == 200
