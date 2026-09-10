"""Explanation: a natural-language rendering of an existing deterministic finding.

An explanation never establishes a fact. It restates what the engine already
found. The provider, model and prompt_version columns record exactly which
system produced the text; ``finding_fingerprint`` ties the row to the
deterministic finding it describes, so a changed finding never reuses a stale
explanation. ``payload`` holds the validated structured reply.
"""

from typing import TYPE_CHECKING, Any

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from app.db.database import Base
from app.db.models.base import ID_LENGTH, CreatedAtMixin, UUIDPrimaryKeyMixin
from app.db.models.enums import ExplanationStatus, enum_column

if TYPE_CHECKING:
    from app.db.models.finding import Finding


class Explanation(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """A generated explanation of one finding."""

    __tablename__ = "explanations"

    finding_id: Mapped[str] = mapped_column(
        String(ID_LENGTH),
        ForeignKey("findings.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    model: Mapped[str] = mapped_column(String(128), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(64), nullable=False)
    # The deterministic finding's fingerprint at generation time. Part of the
    # explanation's cache identity: if the finding changes, its fingerprint
    # changes and this row stops matching.
    finding_fingerprint: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[ExplanationStatus] = mapped_column(
        enum_column(ExplanationStatus, "explanation_status"),
        nullable=False,
        default=ExplanationStatus.PENDING,
    )

    # The validated structured reply (summary / why_it_matters /
    # evidence_explanation / migration_explanation / impact_explanation /
    # limitations). Never contains a deterministic field the model could
    # override.
    payload: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    # Set only when ``status == FAILED``: a stable code and a safe message.
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    what_was_found: Mapped[str | None] = mapped_column(Text, nullable=True)
    what_it_means: Mapped[str | None] = mapped_column(Text, nullable=True)
    why_it_matters: Mapped[str | None] = mapped_column(Text, nullable=True)
    review_action: Mapped[str | None] = mapped_column(Text, nullable=True)

    finding: Mapped["Finding"] = relationship(back_populates="explanations")
