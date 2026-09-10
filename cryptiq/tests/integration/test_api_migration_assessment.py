"""Integration tests for contextual migration assessment endpoints.

Verifies:
- Migration assessment against real persisted findings in DB
- Epistemic integrity: deterministic facts immutable, context injected, authoritative citations
- Full caching lifecycle (miss on first call, hit on identical second call, miss on domain change)
- GET and POST endpoints
- Database audit events recorded (REQUESTED and COMPLETED)
- Database persistence in migration_assessments table
- Guardrails applied end-to-end (hash never mapped to ML-DSA)
- Gemini structured output integration pathway
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.config import get_settings
from app.db.models.audit_event import AuditEvent
from app.db.models.enums import AuditEventType
from app.db.models.migration_assessment import MigrationAssessmentRecord
from app.integrations.gemini import GeminiClient
from app.services.context_advisor import ContextAdvisorService
from tests.integration.conftest import DEMO_COMMIT, DEMO_URL

pytestmark = pytest.mark.usefixtures("run_job")


class _FakeResponse:
    def __init__(self, text: str) -> None:
        self.text = text


class _RecordingGeminiSdk:
    """Stands in for google.genai.Client, recording requests and returning valid structured JSON."""

    def __init__(self, reply_text: str) -> None:
        self.reply_text = reply_text
        self.calls: list[dict] = []
        self.models = self

    def generate_content(self, *, model, contents, config):
        self.calls.append({"model": model, "contents": contents, "config": config})
        return _FakeResponse(self.reply_text)


async def _get_finding_id_by_api(client: TestClient, run_job, api: str) -> str:
    """Trigger scan and return finding ID for a specific API call."""
    created = client.post(
        "/api/v1/inspections",
        json={"repository_url": DEMO_URL, "commit_sha": DEMO_COMMIT},
    ).json()
    await run_job()
    listing = client.get(f"/api/v1/inspections/{created['id']}/findings").json()
    items = listing.get("items", [])
    matching = [i for i in items if i["api"] == api]
    if not matching:
        raise ValueError(f"No finding matching api={api}. Available: {[i['api'] for i in items]}")
    return matching[0]["id"]


# --------------------------------------------------------------------------
# End-to-End Persistence & Cache Lifecycle Test
# --------------------------------------------------------------------------


async def test_migration_assessment_lifecycle_with_persisted_finding(
    api_client: TestClient,
    run_job,
    api_session_factory: sessionmaker[Session],
) -> None:
    """Test the full lifecycle of migration assessments against real persisted findings."""
    finding_id = await _get_finding_id_by_api(api_client, run_job, "RSAPrivateKey.sign")

    # 1. Initial Assessment Request with AUTONOMOUS_DRONE domain profile
    drone_payload = {
        "domain_profile": {
            "domain": "AUTONOMOUS_DRONE",
            "bandwidth_constrained": True,
            "latency_sensitive": True,
            "air_gapped": False,
        }
    }
    resp1 = api_client.post(
        f"/api/v1/findings/{finding_id}/migration-assessment",
        json=drone_payload,
    )
    assert resp1.status_code == 200, resp1.text
    data1 = resp1.json()

    assert data1["finding_id"] == finding_id
    assert data1["cached"] is False
    assert data1["assessment"] == "REVIEW"  # REVIEW due to high bandwidth constraint trade-offs
    assert data1["pqc_migration_required"] is True
    assert data1["migration_candidate"] in ("ML-DSA-65", "ML-DSA")
    assert data1["domain_profile"]["domain"] == "AUTONOMOUS_DRONE"
    assert data1["domain_profile"]["bandwidth_constraint"] == "HIGH"
    assert len(data1["knowledge_sources"]) > 0
    assert any("FIPS 204" in str(ks) or "SP 800-131A" in str(ks) for ks in data1["knowledge_sources"])
    assert len(data1["engineering_tradeoffs"]) > 0
    assert data1["id"] is not None
    record_id = data1["id"]

    # 2. Cache Hit Verification: Exact same request returns cached assessment
    resp2 = api_client.post(
        f"/api/v1/findings/{finding_id}/migration-assessment",
        json=drone_payload,
    )
    assert resp2.status_code == 200
    data2 = resp2.json()
    assert data2["cached"] is True
    assert data2["id"] == record_id
    assert data2["assessment"] == data1["assessment"]
    assert data2["migration_candidate"] == data1["migration_candidate"]

    # 3. Cache Miss Verification: Different domain profile causes fresh assessment
    cloud_payload = {
        "domain_profile": {
            "domain": "CLOUD_INFRASTRUCTURE",
            "bandwidth_constraint": "LOW",
            "latency_sensitivity": "LOW",
        }
    }
    resp3 = api_client.post(
        f"/api/v1/findings/{finding_id}/migration-assessment",
        json=cloud_payload,
    )
    assert resp3.status_code == 200
    data3 = resp3.json()
    assert data3["cached"] is False
    assert data3["id"] != record_id
    assert data3["assessment"] == "MIGRATE"
    assert data3["domain_profile"]["domain"] == "CLOUD_INFRASTRUCTURE"

    # 4. GET Endpoint: Retrieves cached assessment by domain parameter
    get_resp = api_client.get(
        f"/api/v1/findings/{finding_id}/migration-assessment?domain=AUTONOMOUS_DRONE"
    )
    assert get_resp.status_code == 200
    get_data = get_resp.json()
    assert get_data["cached"] is True
    assert get_data["id"] == record_id
    assert get_data["domain_profile"]["domain"] == "AUTONOMOUS_DRONE"

    # 5. Verify Database Audit Events
    with api_session_factory() as session:
        events = session.scalars(
            select(AuditEvent)
            .where(AuditEvent.finding_id == finding_id)
            .order_by(AuditEvent.created_at.asc())
        ).all()

        event_types = [e.event_type for e in events]
        assert AuditEventType.MIGRATION_ASSESSMENT_REQUESTED in event_types
        assert AuditEventType.MIGRATION_ASSESSMENT_COMPLETED in event_types

        # Verify audit metadata
        completed_events = [
            e for e in events if e.event_type == AuditEventType.MIGRATION_ASSESSMENT_COMPLETED
        ]
        assert len(completed_events) >= 2  # At least drone and cloud completed
        assert completed_events[0].event_metadata.get("decision") == "REVIEW"
        assert completed_events[1].event_metadata.get("decision") == "MIGRATE"

    # 6. Verify Database Persistence in migration_assessments table
    with api_session_factory() as session:
        records = session.scalars(
            select(MigrationAssessmentRecord)
            .where(MigrationAssessmentRecord.finding_id == finding_id)
            .order_by(MigrationAssessmentRecord.created_at.asc())
        ).all()

        assert len(records) >= 2
        drone_record = next(r for r in records if r.domain == "AUTONOMOUS_DRONE")
        cloud_record = next(r for r in records if r.domain == "CLOUD_INFRASTRUCTURE")
        assert drone_record.status == "COMPLETED"
        assert drone_record.decision == "REVIEW"
        assert cloud_record.status == "COMPLETED"
        assert cloud_record.decision == "MIGRATE"
        assert drone_record.payload is not None
        assert cloud_record.payload is not None


# --------------------------------------------------------------------------
# Guardrails End-to-End via API: Hash finding never mapped to ML-DSA
# --------------------------------------------------------------------------


async def test_migration_assessment_guardrail_prevents_hash_mapping(
    api_client: TestClient,
    run_job,
) -> None:
    """Verify through the HTTP API that SHA hash findings are protected by guardrails."""
    finding_id = await _get_finding_id_by_api(api_client, run_job, "hashes.SHA1")

    drone_payload = {
        "domain_profile": {
            "domain": "AUTONOMOUS_DRONE",
            "bandwidth_constrained": True,
        }
    }
    resp = api_client.post(
        f"/api/v1/findings/{finding_id}/migration-assessment",
        json=drone_payload,
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()

    assert data["finding_id"] == finding_id
    # Guardrail ensures hashes are never mapped to ML-DSA / ML-KEM
    assert data["migration_candidate"] is None or "ML-DSA" not in str(data["migration_candidate"])
    assert "ML-DSA" not in (data.get("alternatives") or [])
    assert data["assessment"] in ("KEEP", "REVIEW")


# --------------------------------------------------------------------------
# Gemini Structured Output Mock Integration
# --------------------------------------------------------------------------


async def test_migration_assessment_with_gemini_mock(
    api_client: TestClient,
    run_job,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify the Gemini structured response pathway when Gemini SDK is configured."""
    finding_id = await _get_finding_id_by_api(api_client, run_job, "RSAPrivateKey.sign")

    fake_payload = {
        "assessment": "MIGRATE",
        "confidence": "HIGH",
        "contextual_role": "DIGITAL_SIGNATURE",
        "rationale": "Mocked Gemini: RSA signature must be migrated to ML-DSA-65 under FIPS 204.",
        "pqc_migration_required": True,
        "migration_candidate": "ML-DSA-65",
        "alternatives": ["SLH-DSA-SHA2-128s"],
        "engineering_tradeoffs": ["Signature size expands from 256 bytes to ~3.3 KB"],
        "required_context": ["Firmware package size limit"],
        "evidence_interpretation": "Direct call to RSA sign.",
        "limitations": ["Mock model limitation."],
    }
    fake_sdk = _RecordingGeminiSdk(json.dumps(fake_payload))

    # Configure Gemini client with fake SDK
    def _advisor_factory() -> ContextAdvisorService:
        client = GeminiClient(get_settings(), sdk_client=fake_sdk)
        return ContextAdvisorService(gemini_client=client)

    monkeypatch.setattr(
        "app.services.migration_assessments.ContextAdvisorService",
        _advisor_factory,
    )

    resp = api_client.post(
        f"/api/v1/findings/{finding_id}/migration-assessment",
        json={"domain_profile": {"domain": "AUTONOMOUS_DRONE"}},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()

    assert data["cached"] is False
    assert data["assessment"] == "MIGRATE"
    assert data["contextual_role"] == "DIGITAL_SIGNATURE"
    assert "Mocked Gemini" in data["rationale"]
    assert data["migration_candidate"] == "ML-DSA-65"
    assert len(fake_sdk.calls) == 1
    call = fake_sdk.calls[0]
    assert "RSAPrivateKey.sign" in call["contents"]


# --------------------------------------------------------------------------
# Error handling: 404 for missing finding
# --------------------------------------------------------------------------


def test_migration_assessment_nonexistent_finding(api_client: TestClient) -> None:
    """Querying a non-existent finding returns 404."""
    resp = api_client.post(
        "/api/v1/findings/nonexistent-finding-uuid/migration-assessment",
        json={"domain_profile": {"domain": "AUTONOMOUS_DRONE"}},
    )
    assert resp.status_code == 404
