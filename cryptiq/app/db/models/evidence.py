"""Evidence: the exact source span that justifies a finding.

Evidence is immutable. It records the commit, the span and the excerpt as they
were when the rule matched, so a finding can always be re-checked against the
source it was derived from.
"""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base
from app.db.models.base import ID_LENGTH, UUIDPrimaryKeyMixin, utcnow

if TYPE_CHECKING:
    from app.db.models.finding import Finding


class Evidence(UUIDPrimaryKeyMixin, Base):
    """The source span a finding was derived from.

    One row per finding: the unique foreign key is what makes the
    "no finding without evidence" rule checkable in the database.
    """

    __tablename__ = "evidence"

    finding_id: Mapped[str] = mapped_column(
        String(ID_LENGTH),
        ForeignKey("findings.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    repository_sha: Mapped[str] = mapped_column(String(40), nullable=False)
    file_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    start_line: Mapped[int] = mapped_column(Integer, nullable=False)
    end_line: Mapped[int] = mapped_column(Integer, nullable=False)
    source_excerpt: Mapped[str] = mapped_column(Text, nullable=False)
    rule_id: Mapped[str] = mapped_column(String(128), nullable=False)
    parser_version: Mapped[str] = mapped_column(String(64), nullable=False)
    ruleset_version: Mapped[str] = mapped_column(String(64), nullable=False)
    retrieved_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )

    finding: Mapped["Finding"] = relationship(back_populates="evidence")
