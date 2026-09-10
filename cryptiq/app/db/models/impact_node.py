"""ImpactNode: one program element inside a finding's bounded impact."""

from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base
from app.db.models.base import ID_LENGTH, UUIDPrimaryKeyMixin
from app.db.models.enums import Confidence, ImpactNodeType, ImpactRelationship, enum_column

if TYPE_CHECKING:
    from app.db.models.finding import Finding


class ImpactNode(UUIDPrimaryKeyMixin, Base):
    """A program element the finding reaches, and how it is reached."""

    __tablename__ = "impact_nodes"

    finding_id: Mapped[str] = mapped_column(
        String(ID_LENGTH),
        ForeignKey("findings.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    node_type: Mapped[ImpactNodeType] = mapped_column(
        enum_column(ImpactNodeType, "impact_node_type"), nullable=False
    )
    label: Mapped[str] = mapped_column(String(512), nullable=False)
    relationship_type: Mapped[ImpactRelationship | None] = mapped_column(
        "relationship",
        enum_column(ImpactRelationship, "impact_relationship"),
        nullable=True,
    )
    confidence: Mapped[Confidence] = mapped_column(
        enum_column(Confidence, "confidence"), nullable=False
    )

    finding: Mapped["Finding"] = relationship(back_populates="impact_nodes")
