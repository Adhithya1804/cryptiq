"""MigrationAssessment: a contextual post-quantum migration evaluation of a finding.

Persisted for reproducibility, auditability, and caching across scans.
Identified by:
  finding_fingerprint + domain_profile_hash + knowledge_version + prompt_version + model
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sqlalchemy import ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from app.db.database import Base
from app.db.models.base import ID_LENGTH, CreatedAtMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.db.models.finding import Finding


class MigrationAssessmentRecord(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """Stored contextual migration assessment for one finding."""

    __tablename__ = "migration_assessments"
    __table_args__ = (
        Index(
            "ix_migration_assessments_cache_key",
            "finding_fingerprint",
            "domain_profile_hash",
            "knowledge_version",
            "prompt_version",
            "model",
        ),
    )

    finding_id: Mapped[str] = mapped_column(
        String(ID_LENGTH),
        ForeignKey("findings.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    model: Mapped[str | None] = mapped_column(String(128), nullable=True)
    prompt_version: Mapped[str] = mapped_column(String(64), nullable=False)
    knowledge_version: Mapped[str] = mapped_column(String(64), nullable=False)
    finding_fingerprint: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    domain: Mapped[str] = mapped_column(String(64), nullable=False, default="GENERAL_SOFTWARE")
    domain_profile_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)

    status: Mapped[str] = mapped_column(String(32), nullable=False, default="PENDING")
    decision: Mapped[str | None] = mapped_column(String(32), nullable=True)
    confidence: Mapped[str | None] = mapped_column(String(32), nullable=True)
    contextual_role: Mapped[str | None] = mapped_column(String(64), nullable=True)

    # Full structured payload matching ContextualAssessment.to_dict()
    payload: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    finding: Mapped["Finding"] = relationship(back_populates="migration_assessments")
