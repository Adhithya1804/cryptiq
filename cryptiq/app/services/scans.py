"""The scan service: create an inspection, read its state, read its findings.

This is the write path the API was missing. Creating an inspection resolves
the repository, records a :class:`Scan` in ``QUEUED`` and a claimable
:class:`ScanJob`; the worker does the rest. Reads never touch the engine.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from enum import StrEnum

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.db.models.enums import (
    Confidence,
    CryptographicRole,
    ReviewPriority,
    ReviewStatus,
    ScanJobStatus,
    ScanStatus,
)
from app.db.models.finding import Finding
from app.db.models.repository import Repository
from app.db.models.review_item import ReviewItem
from app.db.models.scan import Scan
from app.db.models.scan_job import ScanJob
from app.engine import engine_versions
from app.engine.fingerprints import ScanIdentity
from app.engine.ingestion.validation import normalize_commit_sha
from app.errors import NotFoundError, ValidationError
from app.integrations.github import parse_repository_url
from app.services.scan_cache import find_completed_scan

logger = logging.getLogger(__name__)

#: Hard ceiling on a page size the API will honour, so a client cannot ask for
#: every row by passing a huge ``page_size``.
MAX_PAGE_SIZE = 200
DEFAULT_PAGE_SIZE = 50


def _parse_enum[E: StrEnum](enum_cls: type[E], raw: str, label: str) -> E:
    """Turn a wire token (any casing, ``-``/space separators) into an enum."""
    token = raw.strip().upper().replace("-", "_").replace(" ", "_")
    try:
        return enum_cls(token)
    except ValueError as exc:
        raise ValidationError(f"{raw!r} is not a valid {label}.") from exc


def _upsert_repository(session: Session, url: str) -> Repository:
    """Return the stored repository for a URL, creating it on first sight."""
    reference = parse_repository_url(url)
    existing = session.scalars(
        select(Repository).where(
            Repository.provider == reference.provider,
            Repository.owner == reference.owner,
            Repository.name == reference.name,
        )
    ).first()
    if existing is not None:
        return existing
    repository = Repository(
        provider=reference.provider,
        owner=reference.owner,
        name=reference.name,
        canonical_url=reference.canonical_url,
    )
    session.add(repository)
    session.flush()
    return repository


def create_scan(
    session: Session, repository_url: str, commit_sha: str
) -> tuple[Scan, bool]:
    """Create (or reuse) a scan for a repository at an exact commit.

    Returns ``(scan, cached)``. When ``cached`` is true the returned scan is an
    already-COMPLETED run with the same seven-part identity: the engine is a
    pure function of that identity, so its findings already answer the request
    and nothing new is queued. Otherwise a fresh QUEUED scan and job are
    recorded and ``cached`` is false.
    """
    normalized_sha = normalize_commit_sha(commit_sha)
    repository = _upsert_repository(session, repository_url)

    versions = engine_versions()
    identity = ScanIdentity(
        provider=repository.provider,
        owner=repository.owner,
        name=repository.name,
        commit_sha=normalized_sha,
        parser_version=versions.parser_version,
        ruleset_version=versions.ruleset_version,
        pqc_ruleset_version=versions.pqc_ruleset_version,
    )
    cached = find_completed_scan(session, identity)
    if cached is not None:
        logger.info("reusing completed scan %s for %s", cached.id, repository.name)
        return cached, True

    scan = Scan(
        repository_id=repository.id,
        commit_sha=normalized_sha,
        status=ScanStatus.QUEUED,
    )
    session.add(scan)
    session.flush()
    session.add(ScanJob(scan_id=scan.id, status=ScanJobStatus.QUEUED))
    session.commit()
    session.refresh(scan)
    logger.info("queued scan %s for %s@%s", scan.id, repository.name, normalized_sha)
    return scan, False


def create_inspection(session: Session, repository_url: str, commit_sha: str) -> Scan:
    """Back-compat wrapper: create or reuse a scan, discarding the cached flag."""
    scan, _ = create_scan(session, repository_url, commit_sha)
    return scan


def get_scan(session: Session, scan_id: str) -> Scan:
    scan = session.get(Scan, scan_id)
    if scan is None:
        raise NotFoundError(f"No inspection with id {scan_id!r}.")
    return scan


def get_repository(session: Session, repository_id: str) -> Repository:
    repository = session.get(Repository, repository_id)
    if repository is None:
        raise NotFoundError(f"No project with id {repository_id!r}.")
    return repository


def list_scans(session: Session, *, repository_id: str | None = None) -> list[Scan]:
    statement = select(Scan).order_by(Scan.created_at.desc(), Scan.id.desc())
    if repository_id is not None:
        statement = statement.where(Scan.repository_id == repository_id)
    return list(session.scalars(statement).all())


def list_repositories(session: Session) -> list[Repository]:
    return list(
        session.scalars(
            select(Repository).order_by(Repository.created_at.desc())
        ).all()
    )


def latest_scan_by_repository(session: Session) -> dict[str, Scan]:
    """Return the newest scan for each repository, keyed by repository id."""
    scans = session.scalars(
        select(Scan).order_by(Scan.created_at.desc(), Scan.id.desc())
    ).all()
    latest: dict[str, Scan] = {}
    for scan in scans:
        latest.setdefault(scan.repository_id, scan)
    return latest


def severity_by_scan(
    session: Session, scan_ids: list[str]
) -> dict[str, dict[str, int]]:
    """Return ``{scan_id: {priority band: count}}`` in one grouped query."""
    if not scan_ids:
        return {}
    rows = session.execute(
        select(Finding.scan_id, Finding.priority, func.count())
        .where(Finding.scan_id.in_(scan_ids))
        .group_by(Finding.scan_id, Finding.priority)
    ).all()
    result: dict[str, dict[str, int]] = defaultdict(dict)
    for scan_id, priority, count in rows:
        result[scan_id][priority.value] = count
    return result


def list_findings(session: Session, scan_id: str) -> list[Finding]:
    get_scan(session, scan_id)
    return list(
        session.scalars(
            select(Finding)
            .where(Finding.scan_id == scan_id)
            .options(selectinload(Finding.review_items))
            .order_by(
                Finding.priority_score.desc(),
                Finding.file_path,
                Finding.start_line,
                Finding.id,
            )
        ).all()
    )


def _clamp_page(page: int, page_size: int) -> tuple[int, int]:
    page = max(page, 1)
    page_size = min(max(page_size, 1), MAX_PAGE_SIZE)
    return page, page_size


def _finding_filters(
    *,
    priority: str | None,
    algorithm: str | None,
    role: str | None,
    confidence: str | None,
) -> list:
    """Build the SQLAlchemy conditions common to the findings and queue pages."""
    conditions: list = []
    if priority:
        conditions.append(
            Finding.priority == _parse_enum(ReviewPriority, priority, "priority")
        )
    if role:
        conditions.append(
            Finding.role == _parse_enum(CryptographicRole, role, "role")
        )
    if confidence:
        conditions.append(
            Finding.confidence == _parse_enum(Confidence, confidence, "confidence")
        )
    if algorithm and algorithm.strip():
        conditions.append(
            func.lower(Finding.algorithm).like(f"%{algorithm.strip().lower()}%")
        )
    return conditions


_FINDING_ORDER = (
    Finding.priority_score.desc(),
    Finding.file_path,
    Finding.start_line,
    Finding.id,
)


def list_findings_page(
    session: Session,
    scan_id: str,
    *,
    page: int = 1,
    page_size: int = DEFAULT_PAGE_SIZE,
    priority: str | None = None,
    algorithm: str | None = None,
    role: str | None = None,
    confidence: str | None = None,
    review_status: str | None = None,
) -> tuple[list[Finding], int]:
    """Return one filtered, ordered page of a scan's findings and the grand total.

    Filtering is done in the database; the frontend never receives rows it then
    discards. Ordering matches :func:`list_findings` so a finding keeps its
    place across pages.
    """
    get_scan(session, scan_id)
    page, page_size = _clamp_page(page, page_size)

    conditions = [Finding.scan_id == scan_id]
    conditions += _finding_filters(
        priority=priority, algorithm=algorithm, role=role, confidence=confidence
    )
    statement = select(Finding).where(*conditions)
    if review_status:
        parsed = _parse_enum(ReviewStatus, review_status, "review status")
        statement = statement.join(Finding.review_items).where(
            ReviewItem.status == parsed
        )

    total = int(
        session.scalar(select(func.count()).select_from(statement.subquery())) or 0
    )
    rows = session.scalars(
        statement.options(selectinload(Finding.review_items))
        .order_by(*_FINDING_ORDER)
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return list(rows), total


def list_review_queue_page(
    session: Session,
    *,
    page: int = 1,
    page_size: int = DEFAULT_PAGE_SIZE,
    priority: str | None = None,
    algorithm: str | None = None,
    role: str | None = None,
    review_status: str | None = None,
) -> tuple[list[tuple[ReviewItem, Finding]], int]:
    """One filtered, ordered page of the global review queue and its grand total."""
    page, page_size = _clamp_page(page, page_size)

    conditions = _finding_filters(
        priority=priority, algorithm=algorithm, role=role, confidence=None
    )
    if review_status:
        conditions.append(
            ReviewItem.status == _parse_enum(ReviewStatus, review_status, "review status")
        )
    statement = (
        select(ReviewItem, Finding)
        .join(Finding, ReviewItem.finding_id == Finding.id)
        .where(*conditions)
    )
    total = int(
        session.scalar(select(func.count()).select_from(statement.subquery())) or 0
    )
    rows = session.execute(
        statement.order_by(*_FINDING_ORDER)
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return [(review, finding) for review, finding in rows], total


def get_finding(session: Session, finding_id: str) -> Finding:
    finding = session.scalars(
        select(Finding)
        .where(Finding.id == finding_id)
        .options(
            selectinload(Finding.evidence),
            selectinload(Finding.impact_nodes),
            selectinload(Finding.review_items),
        )
    ).first()
    if finding is None:
        raise NotFoundError(f"No finding with id {finding_id!r}.")
    return finding


def list_review_queue(session: Session) -> list[tuple[ReviewItem, Finding]]:
    """Every review item, most urgent first, paired with its finding.

    Ordered by the finding's priority score descending, then by a stable key,
    so equal scores never swap between requests.
    """
    rows = session.execute(
        select(ReviewItem, Finding)
        .join(Finding, ReviewItem.finding_id == Finding.id)
        .order_by(
            Finding.priority_score.desc(),
            Finding.file_path,
            Finding.start_line,
            Finding.id,
        )
    ).all()
    return [(review, finding) for review, finding in rows]
