"""Finding: a cryptographic construct observed at an immutable source location."""

from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from app.db.database import Base
from app.db.models.base import ID_LENGTH, CreatedAtMixin, UUIDPrimaryKeyMixin
from app.db.models.enums import (
    Confidence,
    CryptographicRole,
    FindingStatus,
    ReviewPriority,
    enum_column,
)

if TYPE_CHECKING:
    from app.db.models.audit_event import AuditEvent
    from app.db.models.evidence import Evidence
    from app.db.models.explanation import Explanation
    from app.db.models.impact_node import ImpactNode
    from app.db.models.review_item import ReviewItem
    from app.db.models.scan import Scan


class Finding(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """One cryptographic construct detected by a deterministic rule.

    The fingerprint identifies the same logical finding across commits, so it
    is unique within a scan. Line and column numbers locate the construct but
    never contribute to its identity.
    """

    __tablename__ = "findings"
    __table_args__ = (
        UniqueConstraint("scan_id", "fingerprint", name="uq_findings_scan_fingerprint"),
        Index("ix_findings_scan_id", "scan_id"),
        Index("ix_findings_fingerprint", "fingerprint"),
        Index("ix_findings_priority", "priority"),
        Index("ix_findings_role", "role"),
    )

    scan_id: Mapped[str] = mapped_column(
        String(ID_LENGTH),
        ForeignKey("scans.id", ondelete="CASCADE"),
        nullable=False,
    )
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)

    algorithm: Mapped[str] = mapped_column(String(128), nullable=False)
    primitive: Mapped[str] = mapped_column(String(128), nullable=False)
    library: Mapped[str] = mapped_column(String(128), nullable=False)
    api: Mapped[str] = mapped_column(String(255), nullable=False)
    operation: Mapped[str] = mapped_column(String(128), nullable=False)

    file_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    start_line: Mapped[int] = mapped_column(Integer, nullable=False)
    end_line: Mapped[int] = mapped_column(Integer, nullable=False)
    start_column: Mapped[int | None] = mapped_column(Integer, nullable=True)
    end_column: Mapped[int | None] = mapped_column(Integer, nullable=True)

    role: Mapped[CryptographicRole] = mapped_column(
        enum_column(CryptographicRole, "cryptographic_role"), nullable=False
    )
    confidence: Mapped[Confidence] = mapped_column(
        enum_column(Confidence, "confidence"), nullable=False
    )
    priority: Mapped[ReviewPriority] = mapped_column(
        enum_column(ReviewPriority, "review_priority"), nullable=False
    )
    # The priority band above is derived from this score and these reasons by
    # the priority stage. They are stored, not recomputed, because rebuilding
    # them would need the RuleMatch and impact graph the engine already
    # consumed. ``role_rationale`` is likewise the fixed sentence the
    # classifier chose.
    priority_score: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    priority_reasons: Mapped[list[str]] = mapped_column(
        JSON, nullable=False, default=list
    )
    role_rationale: Mapped[str] = mapped_column(Text, nullable=False, default="")
    # Why the rule fired (e.g. DIRECT_MODULE_API): the ``EvidenceBasis`` token
    # from the RuleMatch, stored so the hosted API's inference block matches the
    # in-process CLI. Nullable for rows written before this column existed.
    evidence_basis: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[FindingStatus] = mapped_column(
        enum_column(FindingStatus, "finding_status"),
        nullable=False,
        default=FindingStatus.ACTIVE,
    )

    scan: Mapped["Scan"] = relationship(back_populates="findings")
    evidence: Mapped["Evidence"] = relationship(
        back_populates="finding",
        cascade="all, delete-orphan",
        passive_deletes=True,
        uselist=False,
    )
    impact_nodes: Mapped[list["ImpactNode"]] = relationship(
        back_populates="finding",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    review_items: Mapped[list["ReviewItem"]] = relationship(
        back_populates="finding",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    explanations: Mapped[list["Explanation"]] = relationship(
        back_populates="finding",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    audit_events: Mapped[list["AuditEvent"]] = relationship(back_populates="finding")
