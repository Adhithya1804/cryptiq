"""store the priority score, its reasons, and the role rationale on a finding

The API exposes the migration review queue ordered by priority score, and the
Finding Detail screen lists the sentences behind the score and the role. Both
are produced by deterministic engine stages from the RuleMatch and the impact
graph -- neither of which is persisted -- so the values are stored on the
finding rather than recomputed.

New columns, all NOT NULL with a server-safe default so the widening applies
to any existing rows (there are none yet).

Revision ID: e3f4a5b6c7d8
Revises: d2e3f4a5b6c7
Create Date: 2026-09-09 22:02:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e3f4a5b6c7d8"
down_revision: str | None = "d2e3f4a5b6c7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("findings", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "priority_score",
                sa.Integer(),
                nullable=False,
                server_default="0",
            )
        )
        batch_op.add_column(
            sa.Column(
                "priority_reasons",
                sa.JSON(),
                nullable=False,
                server_default="[]",
            )
        )
        batch_op.add_column(
            sa.Column(
                "role_rationale",
                sa.Text(),
                nullable=False,
                server_default="",
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("findings", schema=None) as batch_op:
        batch_op.drop_column("role_rationale")
        batch_op.drop_column("priority_reasons")
        batch_op.drop_column("priority_score")
