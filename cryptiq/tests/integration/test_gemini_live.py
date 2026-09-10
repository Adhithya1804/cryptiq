"""Optional real-Gemini check. Skips cleanly when GEMINI_API_KEY is absent.

Runs one explanation against a single known finding and asserts the contract:
the request succeeds, the structured output validates, the explanation is
persisted, a second request is served from cache, and the deterministic finding
is unchanged. It never sends the repository at large through the model.
"""

from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from app.config import get_settings
from app.db.models.explanation import Explanation
from tests.integration.conftest import DEMO_COMMIT, DEMO_URL

pytestmark = [
    pytest.mark.gemini_live,
    pytest.mark.skipif(
        not os.environ.get("GEMINI_API_KEY"),
        reason="GEMINI_API_KEY not set; skipping the real Gemini integration test",
    ),
    pytest.mark.usefixtures("run_job"),
]


async def test_one_real_explanation_round_trip(
    api_client: TestClient, run_job, api_session_factory: sessionmaker[Session]
) -> None:
    get_settings.cache_clear()  # pick up the real key from the environment
    created = api_client.post(
        "/api/v1/inspections",
        json={"repository_url": DEMO_URL, "commit_sha": DEMO_COMMIT},
    ).json()
    await run_job()
    listing = api_client.get(f"/api/v1/inspections/{created['id']}/findings").json()
    finding_id = next(
        i["id"] for i in listing["items"] if i["api"] == "RSAPrivateKey.sign"
    )

    first = api_client.post(f"/api/v1/findings/{finding_id}/explanation")
    assert first.status_code == 200, first.text
    body = first.json()
    assert body["cached"] is False
    assert body["summary"] and body["evidence_explanation"]
    assert body["prompt_version"] == "gemini-explanation-v1"

    with api_session_factory() as session:
        rows = session.query(Explanation).filter_by(finding_id=finding_id).all()
    assert any(r.status.value == "COMPLETED" and r.payload for r in rows)

    second = api_client.post(f"/api/v1/findings/{finding_id}/explanation")
    assert second.status_code == 200
    assert second.json()["cached"] is True

    detail = api_client.get(f"/api/v1/findings/{finding_id}").json()
    assert detail["observed"]["algorithm"] == "RSA"
    assert detail["inference"]["role"] == "DIGITAL_SIGNATURE"
    get_settings.cache_clear()
