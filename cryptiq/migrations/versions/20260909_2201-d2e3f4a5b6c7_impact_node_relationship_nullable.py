"""allow an impact node to have no relationship

The engine's impact graph has one root node -- the algorithm itself -- which
is not reached *via* any relationship: its ``relationship`` is ``None`` in
``app.engine.impact.models.ImpactNode``. Persisting the graph faithfully means
the ``impact_nodes.relationship`` column has to accept NULL for that row. The
named CHECK constraint is unchanged; only nullability changes.

Revision ID: d2e3f4a5b6c7
Revises: c1d2e3f4a5b6
Create Date: 2026-09-09 22:01:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d2e3f4a5b6c7"
down_revision: str | None = "c1d2e3f4a5b6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_RELATIONSHIP = sa.Enum(
    "USES",
    "CALLS",
    "DEFINED_IN",
    "CONTAINS",
    "IMPORTS",
    name="impact_relationship",
    native_enum=False,
    create_constraint=True,
    length=32,
)


def upgrade() -> None:
    with op.batch_alter_table("impact_nodes", schema=None) as batch_op:
        batch_op.alter_column(
            "relationship",
            existing_type=_RELATIONSHIP,
            nullable=True,
        )


def downgrade() -> None:
    with op.batch_alter_table("impact_nodes", schema=None) as batch_op:
        batch_op.alter_column(
            "relationship",
            existing_type=_RELATIONSHIP,
            nullable=False,
        )
