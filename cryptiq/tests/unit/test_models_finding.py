"""Finding columns, fingerprint persistence and the evidence rule."""

from datetime import datetime

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.integrity import MissingEvidenceError
from app.db.models import Evidence, Finding, Scan
from app.db.models.enums import (
    Confidence,
    CryptographicRole,
    FindingStatus,
    ReviewPriority,
)
from app.engine.fingerprints import fingerprint as make_fingerprint
from tests.conftest import build_finding


def test_finding_persists_its_columns(finding: Finding) -> None:
    assert finding.algorithm == "RSA"
    assert finding.primitive == "PUBLIC_KEY"
    assert finding.library == "cryptography"
    assert finding.api == "rsa.generate_private_key"
    assert finding.operation == "KEY_GENERATION"
    assert finding.file_path == "src/keys.py"
    assert finding.start_line == 10
    assert finding.end_line == 12
    assert finding.role is CryptographicRole.DIGITAL_SIGNATURE
    assert finding.confidence is Confidence.HIGH
    assert finding.priority is ReviewPriority.HIGH
    assert finding.status is FindingStatus.ACTIVE
    assert isinstance(finding.created_at, datetime)


def test_finding_columns_are_nullable_where_specified(finding: Finding) -> None:
    assert finding.start_column is None
    assert finding.end_column is None


def test_finding_columns_accept_a_column_span(session: Session, scan: Scan) -> None:
    stored = build_finding(scan.id, start_column=4, end_column=40)
    session.add(stored)
    session.commit()

    assert stored.start_column == 4
    assert stored.end_column == 40


def test_fingerprint_is_stored_and_queryable(session: Session, finding: Finding) -> None:
    found = session.scalars(
        select(Finding).where(Finding.fingerprint == finding.fingerprint)
    ).one()

    assert found.id == finding.id


def test_fingerprint_uses_the_phase_one_convention(finding: Finding) -> None:
    expected = make_fingerprint(
        "github/pyca/cryptography", "src/keys.py", "rsa-generate"
    )

    assert finding.fingerprint == expected
    assert len(finding.fingerprint) == 64


def test_a_finding_cannot_be_persisted_without_evidence(session: Session, scan: Scan) -> None:
    session.add(
        Finding(
            scan_id=scan.id,
            fingerprint=make_fingerprint("bare"),
            algorithm="RSA",
            primitive="PUBLIC_KEY",
            library="cryptography",
            api="rsa.generate_private_key",
            operation="KEY_GENERATION",
            file_path="src/keys.py",
            start_line=1,
            end_line=1,
            role=CryptographicRole.DIGITAL_SIGNATURE,
            confidence=Confidence.HIGH,
            priority=ReviewPriority.HIGH,
        )
    )

    with pytest.raises(MissingEvidenceError):
        session.commit()


def test_evidence_records_the_commit_and_versions(finding: Finding) -> None:
    evidence = finding.evidence

    assert evidence.repository_sha == "a" * 40
    assert evidence.parser_version == "python-ast-1"
    assert evidence.ruleset_version == "0.3.0"
    assert isinstance(evidence.retrieved_at, datetime)


def test_a_finding_holds_exactly_one_evidence_row(session: Session, finding: Finding) -> None:
    stored = session.scalars(select(Evidence).where(Evidence.finding_id == finding.id)).all()

    assert len(stored) == 1
