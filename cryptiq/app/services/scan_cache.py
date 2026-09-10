"""Reusing a completed scan instead of rerunning it.

The engine is a pure function of a repository, a commit and the three version
stamps. Two scans that share all seven parts must produce the same findings,
so a completed scan can answer for a new request. A scan served this way is
marked CACHED_REAL: the findings are real, but the source was not fetched
again.
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.enums import ScanStatus, SourceState
from app.db.models.repository import Repository
from app.db.models.scan import Scan
from app.engine.fingerprints import ScanIdentity


def identity_of(scan: Scan, repository: Repository) -> ScanIdentity:
    """Return the seven-part identity of a stored scan."""
    return ScanIdentity(
        provider=repository.provider,
        owner=repository.owner,
        name=repository.name,
        commit_sha=scan.commit_sha,
        parser_version=scan.parser_version,
        ruleset_version=scan.ruleset_version,
        pqc_ruleset_version=scan.pqc_ruleset_version,
    )


def find_completed_scan(
    session: Session,
    identity: ScanIdentity,
    *,
    exclude_scan_id: str | None = None,
) -> Scan | None:
    """Return a completed scan matching the identity exactly, or None.

    Only COMPLETED scans qualify. A running, failed or cancelled scan says
    nothing about what the findings would be.
    """
    statement = (
        select(Scan)
        .join(Repository, Scan.repository_id == Repository.id)
        .where(
            Repository.provider == identity.provider,
            Repository.owner == identity.owner,
            Repository.name == identity.name,
            Scan.commit_sha == identity.commit_sha,
            Scan.parser_version == identity.parser_version,
            Scan.ruleset_version == identity.ruleset_version,
            Scan.pqc_ruleset_version == identity.pqc_ruleset_version,
            Scan.status == ScanStatus.COMPLETED,
        )
        # Oldest first: the original run is the canonical one.
        .order_by(Scan.created_at, Scan.id)
    )
    if exclude_scan_id is not None:
        statement = statement.where(Scan.id != exclude_scan_id)

    return session.scalars(statement).first()


def mark_served_from_cache(scan: Scan) -> Scan:
    """Record that a scan's findings were reused rather than recomputed."""
    scan.source_state = SourceState.CACHED_REAL
    return scan
