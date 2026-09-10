"""Persisting an engine result: dedup by fingerprint, review pre-queue, counts."""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models.enums import ReviewStatus, ScanStatus
from app.db.models.finding import Finding
from app.db.models.repository import Repository
from app.db.models.review_item import ReviewItem
from app.db.models.scan import Scan
from app.engine.ingestion import IngestionLimits, RepositoryReference
from app.engine.ingestion.service import build_result
from app.engine.ingestion.source import SourceSnapshot
from app.engine.pipeline import analyze_snapshot
from app.services.persistence import persist_analysis
from tests.support import write_tree

_LIMITS = IngestionLimits(
    max_archive_bytes=1 << 20,
    max_extracted_bytes=1 << 20,
    max_files=50,
    max_file_bytes=8192,
)

# Two SHA-256 constructions at module scope in one file: same rule, api,
# operation, no enclosing function or class -> one fingerprint, two matches.
COLLIDING_TREE: dict[str, bytes] = {
    "h.py": (
        b"from cryptography.hazmat.primitives import hashes\n"
        b"a = hashes.SHA256()\n"
        b"b = hashes.SHA256()\n"
    ),
}


@pytest.fixture
def colliding_analysis(tmp_path: Path):
    root = write_tree(tmp_path / "snap", COLLIDING_TREE)
    snapshot = SourceSnapshot(
        root_path=root,
        repository=RepositoryReference(
            provider="github",
            owner="pyca",
            name="cryptography",
            canonical_url="https://github.com/pyca/cryptography",
        ),
        commit_sha="1" * 40,
        content_hash="0" * 64,
        file_count=1,
    )
    return analyze_snapshot(build_result(snapshot, _LIMITS), root)


def _scan(session: Session) -> Scan:
    repo = Repository(
        provider="github",
        owner="pyca",
        name="cryptography",
        canonical_url="https://github.com/pyca/cryptography",
    )
    session.add(repo)
    session.flush()
    scan = Scan(repository_id=repo.id, commit_sha="1" * 40, status=ScanStatus.RUNNING)
    session.add(scan)
    session.flush()
    return scan


def test_a_fingerprint_collision_is_folded_into_one_row(
    session: Session, colliding_analysis
) -> None:
    # The engine really does emit two matches with one fingerprint here.
    assert len(colliding_analysis.findings) == 2
    assert len({f.fingerprint for f in colliding_analysis.findings}) == 1

    scan = _scan(session)
    persist_analysis(session, scan, colliding_analysis)
    session.commit()

    rows = session.scalars(select(Finding).where(Finding.scan_id == scan.id)).all()
    assert len(rows) == 1
    assert scan.finding_count == 1
    assert rows[0].start_line == 2  # the first occurrence is kept


def test_migration_candidates_are_pre_queued_for_review(
    session: Session, analysis_result, tmp_path: Path
) -> None:
    analysis = analysis_result(tmp_path)
    scan = _scan(session)
    persist_analysis(session, scan, analysis)
    session.commit()

    candidates = [
        f for f in session.scalars(select(Finding).where(Finding.scan_id == scan.id))
        if any(item.status == ReviewStatus.OPEN for item in f.review_items)
    ]
    # The RSA signature is a candidate; the SHA-1 hash is not.
    algos = {f.algorithm for f in candidates}
    assert "RSA" in algos
    assert "SHA-1" not in algos

    open_reviews = session.scalar(
        select(func.count()).select_from(ReviewItem)
    )
    assert open_reviews == len(candidates)
