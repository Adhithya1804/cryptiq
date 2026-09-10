"""persist the enclosing scope and the evidence basis on a finding

The API's "observed" block advertises ``enclosing_function`` / ``enclosing_class``
and its "inference" block advertises ``evidence_basis``. All three are produced
by the deterministic engine on every RuleMatch, and the in-process CLI already
reports them, but they were never persisted -- so the hosted API and the web UI
always returned null while the CLI returned real values. These columns close
that local/API gap.

All three are nullable: a match at module scope has no enclosing function or
class, and rows written before this revision have neither value.

Revision ID: a5b6c7d8e9f0
Revises: f4a5b6c7d8e9
Create Date: 2026-09-10 08:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a5b6c7d8e9f0"
down_revision: str | None = "f4a5b6c7d8e9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("evidence", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("enclosing_function", sa.String(length=255), nullable=True)
        )
        batch_op.add_column(
            sa.Column("enclosing_class", sa.String(length=255), nullable=True)
        )
    with op.batch_alter_table("findings", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("evidence_basis", sa.String(length=64), nullable=True)
        )


def downgrade() -> None:
    with op.batch_alter_table("findings", schema=None) as batch_op:
        batch_op.drop_column("evidence_basis")
    with op.batch_alter_table("evidence", schema=None) as batch_op:
        batch_op.drop_column("enclosing_class")
        batch_op.drop_column("enclosing_function")
