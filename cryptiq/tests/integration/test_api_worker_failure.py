"""A scan whose source cannot be fetched ends in a real FAILED state."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from tests.integration.conftest import DEMO_COMMIT, DEMO_URL, BrokenSourceProvider


@pytest.fixture
def failing_run_job(monkeypatch, api_session_factory: sessionmaker):
    from app import worker

    monkeypatch.setattr(worker, "SessionLocal", api_session_factory)
    monkeypatch.setattr(worker, "GitHubSourceProvider", BrokenSourceProvider)

    async def _run() -> bool:
        return await worker.run_next_job()

    return _run


async def test_missing_commit_surfaces_as_a_failed_inspection(
    api_client: TestClient, failing_run_job
) -> None:
    created = api_client.post(
        "/api/v1/inspections",
        json={"repository_url": DEMO_URL, "commit_sha": DEMO_COMMIT},
    ).json()

    # Three attempts, then FAILED (DEFAULT_MAX_ATTEMPTS).
    for _ in range(3):
        await failing_run_job()

    body = api_client.get(f"/api/v1/inspections/{created['id']}").json()
    assert body["status"] == "FAILED"
    assert body["error_code"] == "COMMIT_NOT_FOUND"
    assert body["error_message"]
    # No internal detail leaks.
    assert "Traceback" not in body["error_message"]
    assert body["findings_count"] == 0
