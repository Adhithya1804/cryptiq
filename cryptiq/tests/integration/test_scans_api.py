"""The canonical ``/api/v1/scans`` + ``/api/v1/review-items`` surface.

Covers the three things these routes add over ``/inspections``: the
202-queued / 200-cached distinction on submit, the paginated and
server-filtered findings page, and the id-keyed review-item PATCH.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from tests.integration.conftest import DEMO_COMMIT, DEMO_URL

pytestmark = pytest.mark.usefixtures("run_job")


def _submit(client: TestClient) -> dict:
    response = client.post(
        "/api/v1/scans",
        json={"repository_url": DEMO_URL, "commit_sha": DEMO_COMMIT},
    )
    assert response.status_code == 202, response.text
    body = response.json()
    assert body["status"] == "QUEUED"
    assert body["cached"] is False
    return body


async def test_submit_queues_with_202(api_client: TestClient) -> None:
    _submit(api_client)


async def test_resubmit_after_completion_is_served_from_cache(
    api_client: TestClient, run_job
) -> None:
    first = _submit(api_client)
    await run_job()

    again = api_client.post(
        "/api/v1/scans",
        json={"repository_url": DEMO_URL, "commit_sha": DEMO_COMMIT},
    )
    assert again.status_code == 200, again.text
    body = again.json()
    assert body["cached"] is True
    assert body["id"] == first["id"]
    assert body["status"] == "COMPLETED"


async def test_get_scan_mirrors_the_inspection_route(
    api_client: TestClient, run_job
) -> None:
    scan = _submit(api_client)
    await run_job()

    a = api_client.get(f"/api/v1/scans/{scan['id']}").json()
    b = api_client.get(f"/api/v1/inspections/{scan['id']}").json()
    assert a["id"] == b["id"] == scan["id"]
    assert a["status"] == "COMPLETED"
    assert a["findings_count"] == b["findings_count"]


async def test_get_scan_404_for_unknown_id(api_client: TestClient) -> None:
    missing = api_client.get("/api/v1/scans/does-not-exist")
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "not_found"


async def test_findings_page_reports_pagination_metadata(
    api_client: TestClient, run_job
) -> None:
    scan = _submit(api_client)
    await run_job()

    everything = api_client.get(f"/api/v1/scans/{scan['id']}/findings").json()
    total = everything["total"]
    assert total >= 2
    assert everything["page"] == 1
    assert everything["page_size"] == 50
    assert everything["pages"] == 1
    assert len(everything["items"]) == total

    first = api_client.get(
        f"/api/v1/scans/{scan['id']}/findings", params={"page": 1, "page_size": 1}
    ).json()
    assert first["page"] == 1
    assert first["page_size"] == 1
    assert first["total"] == total
    assert first["pages"] == total
    assert len(first["items"]) == 1

    second = api_client.get(
        f"/api/v1/scans/{scan['id']}/findings", params={"page": 2, "page_size": 1}
    ).json()
    assert len(second["items"]) == 1
    assert second["items"][0]["id"] != first["items"][0]["id"]


async def test_findings_page_filters_server_side(
    api_client: TestClient, run_job
) -> None:
    scan = _submit(api_client)
    await run_job()
    url = f"/api/v1/scans/{scan['id']}/findings"

    by_algo = api_client.get(url, params={"algorithm": "rsa"}).json()
    assert by_algo["total"] >= 1
    assert {item["algorithm"] for item in by_algo["items"]} == {"RSA"}

    by_role = api_client.get(url, params={"role": "digital_signature"}).json()
    assert by_role["total"] >= 1
    assert all(item["role"] == "DIGITAL_SIGNATURE" for item in by_role["items"])

    by_priority = api_client.get(url, params={"priority": "high"}).json()
    assert all(item["priority"] == "HIGH" for item in by_priority["items"])

    none = api_client.get(url, params={"algorithm": "kyber"}).json()
    assert none["total"] == 0
    assert none["items"] == []

    bad = api_client.get(url, params={"priority": "not-a-band"})
    assert bad.status_code == 422


async def test_findings_page_filters_by_review_status(
    api_client: TestClient, run_job
) -> None:
    scan = _submit(api_client)
    await run_job()
    url = f"/api/v1/scans/{scan['id']}/findings"

    open_items = api_client.get(url, params={"status": "open"}).json()
    assert open_items["total"] >= 1
    assert all(item["review_status"] == "OPEN" for item in open_items["items"])

    in_review = api_client.get(url, params={"status": "in_review"}).json()
    assert in_review["total"] == 0


def _rsa_review_id(client: TestClient, scan_id: str) -> tuple[str, str]:
    listing = client.get(f"/api/v1/scans/{scan_id}/findings").json()
    rsa = next(i for i in listing["items"] if i["api"] == "RSAPrivateKey.sign")
    detail = client.get(f"/api/v1/findings/{rsa['id']}").json()
    return detail["review"]["id"], rsa["id"]


async def test_patch_review_item_moves_through_the_workflow(
    api_client: TestClient, run_job
) -> None:
    scan = _submit(api_client)
    await run_job()
    review_id, finding_id = _rsa_review_id(api_client, scan["id"])

    started = api_client.patch(
        f"/api/v1/review-items/{review_id}",
        json={"status": "IN_REVIEW", "assigned_to": "alice", "note": "looking"},
    )
    assert started.status_code == 200, started.text
    assert started.json()["status"] == "IN_REVIEW"
    assert started.json()["assigned_to"] == "alice"
    assert started.json()["note"] == "looking"

    resolved = api_client.patch(
        f"/api/v1/review-items/{review_id}", json={"status": "REVIEWED"}
    )
    assert resolved.status_code == 200, resolved.text
    assert resolved.json()["status"] == "RESOLVED"
    # assigned_to / note were not sent again -> unchanged.
    assert resolved.json()["assigned_to"] == "alice"
    assert resolved.json()["note"] == "looking"

    # And it is visible on a fresh finding read.
    detail = api_client.get(f"/api/v1/findings/{finding_id}").json()
    assert detail["review"]["status"] == "RESOLVED"


async def test_patch_review_item_can_clear_assignment(
    api_client: TestClient, run_job
) -> None:
    scan = _submit(api_client)
    await run_job()
    review_id, _ = _rsa_review_id(api_client, scan["id"])

    api_client.patch(
        f"/api/v1/review-items/{review_id}", json={"assigned_to": "bob"}
    )
    cleared = api_client.patch(
        f"/api/v1/review-items/{review_id}", json={"assigned_to": None}
    )
    assert cleared.status_code == 200
    assert cleared.json()["assigned_to"] is None


async def test_patch_review_item_rejects_unknown_id_and_bad_status(
    api_client: TestClient, run_job
) -> None:
    scan = _submit(api_client)
    await run_job()
    review_id, _ = _rsa_review_id(api_client, scan["id"])

    missing = api_client.patch(
        "/api/v1/review-items/nope", json={"status": "IN_REVIEW"}
    )
    assert missing.status_code == 404

    bad = api_client.patch(
        f"/api/v1/review-items/{review_id}", json={"status": "TELEPORTED"}
    )
    assert bad.status_code == 422


async def test_review_queue_paginates_when_asked(
    api_client: TestClient, run_job
) -> None:
    _submit(api_client)
    await run_job()

    full = api_client.get("/api/v1/review-queue").json()
    assert full["total"] == len(full["items"])

    paged = api_client.get(
        "/api/v1/review-queue", params={"page": 1, "page_size": 1}
    ).json()
    assert paged["total"] == full["total"]
    assert len(paged["items"]) == min(1, full["total"])

    filtered = api_client.get(
        "/api/v1/review-queue", params={"algorithm": "rsa"}
    ).json()
    assert all(item["algorithm"] == "RSA" for item in filtered["items"])
