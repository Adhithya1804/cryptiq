"""End-to-end HTTP flow: submit an inspection, run it, read it back.

The source provider is faked, but every other layer is real: the routers, the
services, the worker, persistence, and the wire serialisation the frontend
consumes.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from tests.integration.conftest import DEMO_COMMIT, DEMO_URL

pytestmark = pytest.mark.usefixtures("run_job")


def _create(client: TestClient) -> dict:
    response = client.post(
        "/api/v1/inspections",
        json={"repository_url": DEMO_URL, "commit_sha": DEMO_COMMIT},
    )
    assert response.status_code == 201, response.text
    return response.json()


async def test_submit_returns_a_queued_inspection(api_client: TestClient) -> None:
    body = _create(api_client)

    assert body["status"] == "QUEUED"
    assert body["commit_sha"] == DEMO_COMMIT
    assert body["repository"]["owner"] == "pyca"
    assert body["repository"]["name"] == "cryptography"
    assert body["findings_count"] == 0
    assert body["id"]


async def test_worker_takes_it_to_completed(api_client: TestClient, run_job) -> None:
    inspection = _create(api_client)

    processed = await run_job()
    assert processed is True

    body = api_client.get(f"/api/v1/inspections/{inspection['id']}").json()
    assert body["status"] == "COMPLETED"
    assert body["findings_count"] >= 2
    assert body["files_analyzed"] >= 1
    assert body["duration_ms"] is not None
    assert body["severity"]["high"] >= 1  # the RSA signature


async def test_findings_list_and_detail(api_client: TestClient, run_job) -> None:
    inspection = _create(api_client)
    await run_job()

    listing = api_client.get(
        f"/api/v1/inspections/{inspection['id']}/findings"
    ).json()
    assert listing["total"] == len(listing["items"])
    rsa = next(
        item for item in listing["items"] if item["api"] == "RSAPrivateKey.sign"
    )
    assert rsa["algorithm"] == "RSA"
    assert rsa["role"] == "DIGITAL_SIGNATURE"
    assert rsa["review_path"] == "ML-DSA / SLH-DSA"
    assert rsa["is_migration_candidate"] is True
    assert rsa["priority_score"] > 0

    detail = api_client.get(f"/api/v1/findings/{rsa['id']}").json()
    assert set(detail) >= {
        "id",
        "scan_id",
        "repository",
        "commit_sha",
        "observed",
        "inference",
        "migration",
        "impact",
        "priority",
        "review",
    }
    # Observed facts stay separate from the inference.
    assert "role" not in detail["observed"]
    assert "confidence" not in detail["observed"]
    assert detail["observed"]["algorithm"] == "RSA"
    assert detail["observed"]["source_excerpt"].strip() == "return key.sign(payload)"
    assert detail["inference"]["role"] == "DIGITAL_SIGNATURE"
    assert detail["inference"]["rationale"]
    assert detail["migration"]["is_migration_candidate"] is True
    assert detail["impact"]["scope"] == "STATICALLY_OBSERVED"
    assert detail["impact"]["node_count"] == len(detail["impact"]["nodes"])
    assert detail["priority"]["level"] in {"HIGH", "MEDIUM", "LOW"}
    # A migration candidate is pre-queued for review.
    assert detail["review"]["status"] == "OPEN"
    # No Gemini key configured in the test environment.
    assert detail["ai_explanation_available"] is False


async def test_review_disposition_persists_and_appears_in_the_queue(
    api_client: TestClient, run_job
) -> None:
    inspection = _create(api_client)
    await run_job()
    listing = api_client.get(
        f"/api/v1/inspections/{inspection['id']}/findings"
    ).json()
    rsa = next(
        item for item in listing["items"] if item["api"] == "RSAPrivateKey.sign"
    )

    updated = api_client.post(
        f"/api/v1/findings/{rsa['id']}/review",
        json={"status": "RESOLVED", "note": "handled in ticket 42"},
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["status"] == "RESOLVED"
    assert updated.json()["note"] == "handled in ticket 42"

    # A reload reflects the authoritative state.
    detail = api_client.get(f"/api/v1/findings/{rsa['id']}").json()
    assert detail["review"]["status"] == "RESOLVED"

    queue = api_client.get("/api/v1/review-queue").json()
    entry = next(item for item in queue["items"] if item["finding_id"] == rsa["id"])
    assert entry["status"] == "RESOLVED"
    assert entry["priority_score"] == rsa["priority_score"]
    assert entry["reasons"]


async def test_illegal_review_transition_is_rejected(
    api_client: TestClient, run_job
) -> None:
    inspection = _create(api_client)
    await run_job()
    listing = api_client.get(
        f"/api/v1/inspections/{inspection['id']}/findings"
    ).json()
    finding_id = listing["items"][0]["id"]

    bad = api_client.post(
        f"/api/v1/findings/{finding_id}/review", json={"status": "NONSENSE"}
    )
    assert bad.status_code == 422
    assert bad.json()["error"]["code"] == "validation_error"


async def test_history_and_projects_reflect_the_scan(
    api_client: TestClient, run_job
) -> None:
    inspection = _create(api_client)
    await run_job()

    history = api_client.get("/api/v1/inspections").json()
    assert any(row["id"] == inspection["id"] for row in history["items"])

    projects = api_client.get("/api/v1/projects").json()
    project = next(
        row for row in projects["items"] if row["repository"]["name"] == "cryptography"
    )
    assert project["latest_inspection_status"] == "COMPLETED"
    assert project["findings_count"] >= 2

    project_inspections = api_client.get(
        f"/api/v1/projects/{project['id']}/inspections"
    ).json()
    assert any(row["id"] == inspection["id"] for row in project_inspections["items"])


async def test_a_repeated_submit_reuses_the_completed_scan(
    api_client: TestClient, run_job
) -> None:
    first = _create(api_client)
    await run_job()

    second = api_client.post(
        "/api/v1/inspections",
        json={"repository_url": DEMO_URL, "commit_sha": DEMO_COMMIT},
    ).json()

    assert second["id"] == first["id"]
    assert second["status"] == "COMPLETED"


async def test_unknown_ids_return_the_error_contract(api_client: TestClient) -> None:
    missing_inspection = api_client.get("/api/v1/inspections/does-not-exist")
    assert missing_inspection.status_code == 404
    assert missing_inspection.json()["error"]["code"] == "not_found"

    missing_finding = api_client.get("/api/v1/findings/does-not-exist")
    assert missing_finding.status_code == 404


async def test_cors_allows_the_dev_origin(api_client: TestClient) -> None:
    response = api_client.get(
        "/api/v1/inspections",
        headers={"Origin": "http://localhost:5173"},
    )
    assert response.headers.get("access-control-allow-origin") == "http://localhost:5173"
