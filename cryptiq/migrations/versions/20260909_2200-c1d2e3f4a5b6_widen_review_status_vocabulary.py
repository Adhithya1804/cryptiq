"""widen the review status vocabulary to the four dispositions

The Finding Detail screen records one of four dispositions on a finding:
Mark Resolved, Accept Risk, False Positive, or Keep Open. The persisted
``review_items.status`` enum held only OPEN / IN_REVIEW / REVIEWED, so the
column's CHECK constraint has to accept RESOLVED, ACCEPTED_RISK and
FALSE_POSITIVE as well. REVIEWED stays in the constraint as a legacy alias
for RESOLVED; no code writes it any more.

No rows are translated: this is a widening only.

Revision ID: c1d2e3f4a5b6
Revises: b87f2119dbab
Create Date: 2026-09-09 22:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c1d2e3f4a5b6"
down_revision: str | None = "b87f2119dbab"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

OLD_STATUSES = ("OPEN", "IN_REVIEW", "REVIEWED")
NEW_STATUSES = (
    "OPEN",
    "IN_REVIEW",
    "RESOLVED",
    "ACCEPTED_RISK",
    "FALSE_POSITIVE",
    "REVIEWED",
)


def _enum(values: tuple[str, ...]) -> sa.Enum:
    return sa.Enum(
        *values,
        name="review_status",
        native_enum=False,
        create_constraint=True,
        length=32,
    )


def _rewrite(values: tuple[str, ...]) -> None:
    with op.batch_alter_table("review_items", schema=None) as batch_op:
        batch_op.drop_constraint("review_status", type_="check")
        batch_op.alter_column(
            "status",
            existing_type=sa.String(length=32),
            type_=_enum(values),
            existing_nullable=False,
        )


def upgrade() -> None:
    """Accept the four dispositions on review_items.status."""
    _rewrite(NEW_STATUSES)


def downgrade() -> None:
    """Restore the narrow OPEN / IN_REVIEW / REVIEWED constraint."""
    _rewrite(OLD_STATUSES)
