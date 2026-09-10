"""AuditEvent: an append-only record of pipeline transitions."""

from typing import TYPE_CHECKING, Any

from sqlalchemy import ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from app.db.database import Base
from app.db.models.base import ID_LENGTH, CreatedAtMixin, UUIDPrimaryKeyMixin
from app.db.models.enums import AuditEventType, enum_column

if TYPE_CHECKING:
    from app.db.models.finding import Finding
    from app.db.models.scan import Scan


class AuditEvent(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """One recorded transition, optionally tied to a scan or a finding.

    Deleting a scan or finding sets the reference to NULL instead of removing
    the event: the audit trail must outlive the records it describes.
    """

    __tablename__ = "audit_events"
    __table_args__ = (
        Index("ix_audit_events_scan_id", "scan_id"),
        Index("ix_audit_events_finding_id", "finding_id"),
    )

    scan_id: Mapped[str | None] = mapped_column(
        String(ID_LENGTH),
        ForeignKey("scans.id", ondelete="SET NULL"),
        nullable=True,
    )
    finding_id: Mapped[str | None] = mapped_column(
        String(ID_LENGTH),
        ForeignKey("findings.id", ondelete="SET NULL"),
        nullable=True,
    )
    event_type: Mapped[AuditEventType] = mapped_column(
        enum_column(AuditEventType, "audit_event_type"), nullable=False
    )
    # "metadata" is reserved on the declarative base, so the attribute is
    # renamed while the column keeps the specified name. Generic JSON maps to
    # PostgreSQL JSON and to SQLite's JSON1 text storage.
    event_metadata: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSON, nullable=False, default=dict
    )

    scan: Mapped["Scan | None"] = relationship(back_populates="audit_events")
    finding: Mapped["Finding | None"] = relationship(back_populates="audit_events")
