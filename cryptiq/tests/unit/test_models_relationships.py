"""Relationships and cascade behaviour across the domain model."""

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.models import (
    AuditEvent,
    Evidence,
    Explanation,
    Finding,
    ImpactNode,
    Repository,
    ReviewItem,
    Scan,
    ScanJob,
)
from app.db.models.enums import (
    AuditEventType,
    Confidence,
    ExplanationStatus,
    ImpactNodeType,
    ImpactRelationship,
    ReviewStatus,
)
from tests.conftest import build_finding


def test_repository_lists_its_scans(session: Session, repository: Repository, scan: Scan) -> None:
    session.refresh(repository)

    assert [s.id for s in repository.scans] == [scan.id]
    assert scan.repository.id == repository.id


def test_scan_lists_its_jobs(session: Session, scan: Scan) -> None:
    job = ScanJob(scan_id=scan.id)
    session.add(job)
    session.commit()
    session.refresh(scan)

    assert [j.id for j in scan.jobs] == [job.id]
    assert job.scan.id == scan.id


def test_scan_lists_its_findings(session: Session, scan: Scan, finding: Finding) -> None:
    session.refresh(scan)

    assert [f.id for f in scan.findings] == [finding.id]
    assert finding.scan.id == scan.id


def test_finding_has_evidence(session: Session, finding: Finding) -> None:
    session.refresh(finding)

    assert finding.evidence is not None
    assert finding.evidence.finding_id == finding.id
    assert finding.evidence.rule_id == "rsa-key-generation"
    assert finding.evidence.finding.id == finding.id


def test_finding_lists_its_impact_nodes(session: Session, finding: Finding) -> None:
    node = ImpactNode(
        finding_id=finding.id,
        node_type=ImpactNodeType.FUNCTION,
        label="src/keys.py:generate_key",
        relationship_type=ImpactRelationship.CALLS,
        confidence=Confidence.MEDIUM,
    )
    session.add(node)
    session.commit()
    session.refresh(finding)

    assert [n.id for n in finding.impact_nodes] == [node.id]
    assert node.finding.id == finding.id
    assert node.relationship_type is ImpactRelationship.CALLS


def test_finding_lists_its_review_items(session: Session, finding: Finding) -> None:
    item = ReviewItem(finding_id=finding.id)
    session.add(item)
    session.commit()
    session.refresh(finding)

    assert [i.id for i in finding.review_items] == [item.id]
    assert item.status is ReviewStatus.OPEN
    assert item.assigned_to is None
    assert item.note is None
    assert item.finding.id == finding.id


def test_finding_lists_its_explanations(session: Session, finding: Finding) -> None:
    explanation = Explanation(
        finding_id=finding.id,
        provider="gemini",
        model="gemini-2.5-flash",
        prompt_version="1",
    )
    session.add(explanation)
    session.commit()
    session.refresh(finding)

    assert [e.id for e in finding.explanations] == [explanation.id]
    assert explanation.status is ExplanationStatus.PENDING
    assert explanation.summary is None
    assert explanation.what_was_found is None
    assert explanation.what_it_means is None
    assert explanation.why_it_matters is None
    assert explanation.review_action is None
    assert explanation.finding.id == finding.id


def test_audit_event_links_a_scan_and_a_finding(
    session: Session, scan: Scan, finding: Finding
) -> None:
    event = AuditEvent(
        scan_id=scan.id,
        finding_id=finding.id,
        event_type=AuditEventType.FINDING_CREATED,
        event_metadata={"rule_id": "rsa-key-generation"},
    )
    session.add(event)
    session.commit()

    assert event.scan.id == scan.id
    assert event.finding.id == finding.id
    assert event.event_metadata == {"rule_id": "rsa-key-generation"}


def test_audit_event_references_are_optional(session: Session) -> None:
    event = AuditEvent(event_type=AuditEventType.SCAN_CREATED)
    session.add(event)
    session.commit()

    assert event.scan_id is None
    assert event.finding_id is None
    assert event.event_metadata == {}


def test_deleting_a_repository_removes_its_scans_and_findings(
    session: Session, repository: Repository, finding: Finding
) -> None:
    session.delete(repository)
    session.commit()

    assert session.scalars(select(Scan)).all() == []
    assert session.scalars(select(Finding)).all() == []
    assert session.scalars(select(Evidence)).all() == []


def test_deleting_a_finding_keeps_its_audit_events(session: Session, finding: Finding) -> None:
    event = AuditEvent(finding_id=finding.id, event_type=AuditEventType.FINDING_CREATED)
    session.add(event)
    session.commit()

    session.delete(finding)
    session.commit()
    session.refresh(event)

    assert event.finding_id is None


def test_two_findings_in_a_scan_cannot_share_a_fingerprint(
    session: Session, scan: Scan, finding: Finding
) -> None:
    session.add(build_finding(scan.id, fingerprint=finding.fingerprint, file_path="src/other.py"))

    with pytest.raises(IntegrityError):
        session.commit()


def test_the_same_fingerprint_may_appear_in_another_scan(
    session: Session, repository: Repository, finding: Finding
) -> None:
    later_scan = Scan(repository_id=repository.id, commit_sha="d" * 40)
    session.add(later_scan)
    session.commit()

    session.add(build_finding(later_scan.id, fingerprint=finding.fingerprint))
    session.commit()

    stored = session.scalars(select(Finding).where(Finding.fingerprint == finding.fingerprint))
    assert len(stored.all()) == 2
