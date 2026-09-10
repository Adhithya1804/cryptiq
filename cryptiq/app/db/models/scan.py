"""Scan: one deterministic analysis of a repository at an exact commit."""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base
from app.db.models.base import ID_LENGTH, CreatedAtMixin, UUIDPrimaryKeyMixin
from app.db.models.enums import ScanStatus, SourceState, enum_column
from app.engine import engine_versions

if TYPE_CHECKING:
    from app.db.models.audit_event import AuditEvent
    from app.db.models.finding import Finding
    from app.db.models.repository import Repository
    from app.db.models.scan_job import ScanJob


def _parser_version() -> str:
    return engine_versions().parser_version


def _ruleset_version() -> str:
    return engine_versions().ruleset_version


def _pqc_ruleset_version() -> str:
    return engine_versions().pqc_ruleset_version


class Scan(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """A single analysis run.

    The three version columns are what make a scan reproducible: the same
    commit analysed by the same parser and rule sets must produce the same
    findings, and a version change invalidates a cached result.
    """

    __tablename__ = "scans"
    __table_args__ = (
        Index("ix_scans_repository_id", "repository_id"),
        Index("ix_scans_commit_sha", "commit_sha"),
        Index("ix_scans_status", "status"),
    )

    repository_id: Mapped[str] = mapped_column(
        String(ID_LENGTH),
        ForeignKey("repositories.id", ondelete="CASCADE"),
        nullable=False,
    )
    commit_sha: Mapped[str] = mapped_column(String(40), nullable=False)
    base_commit_sha: Mapped[str | None] = mapped_column(String(40), nullable=True)

    status: Mapped[ScanStatus] = mapped_column(
        enum_column(ScanStatus, "scan_status"),
        nullable=False,
        default=ScanStatus.QUEUED,
    )
    source_state: Mapped[SourceState] = mapped_column(
        enum_column(SourceState, "source_state"),
        nullable=False,
        default=SourceState.UNAVAILABLE,
    )

    parser_version: Mapped[str] = mapped_column(
        String(64), nullable=False, default=_parser_version
    )
    ruleset_version: Mapped[str] = mapped_column(
        String(64), nullable=False, default=_ruleset_version
    )
    pqc_ruleset_version: Mapped[str] = mapped_column(
        String(64), nullable=False, default=_pqc_ruleset_version
    )

    file_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    analyzed_file_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    skipped_file_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    finding_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    repository: Mapped["Repository"] = relationship(back_populates="scans")
    jobs: Mapped[list["ScanJob"]] = relationship(
        back_populates="scan",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    findings: Mapped[list["Finding"]] = relationship(
        back_populates="scan",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    audit_events: Mapped[list["AuditEvent"]] = relationship(back_populates="scan")
