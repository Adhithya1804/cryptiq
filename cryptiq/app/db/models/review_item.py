"""ReviewItem: the human review workflow for a finding.

Review state lives here, not on Finding. Finding.status describes the finding
itself across scans; a finding can be re-reviewed without its own status
changing.
"""

from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base
from app.db.models.base import ID_LENGTH, CreatedAtMixin, UpdatedAtMixin, UUIDPrimaryKeyMixin
from app.db.models.enums import ReviewStatus, enum_column

if TYPE_CHECKING:
    from app.db.models.finding import Finding


class ReviewItem(UUIDPrimaryKeyMixin, CreatedAtMixin, UpdatedAtMixin, Base):
    """One entry in the migration review queue."""

    __tablename__ = "review_items"
    __table_args__ = (
        Index("ix_review_items_finding_id", "finding_id"),
        Index("ix_review_items_status", "status"),
    )

    finding_id: Mapped[str] = mapped_column(
        String(ID_LENGTH),
        ForeignKey("findings.id", ondelete="CASCADE"),
        nullable=False,
    )
    status: Mapped[ReviewStatus] = mapped_column(
        enum_column(ReviewStatus, "review_status"),
        nullable=False,
        default=ReviewStatus.OPEN,
    )
    assigned_to: Mapped[str | None] = mapped_column(String(255), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)

    finding: Mapped["Finding"] = relationship(back_populates="review_items")
