"""widen explanations for structured, fingerprint-scoped Gemini output

The Gemini explanation layer stores a validated structured payload rather than
one free-text blob, ties each row to the deterministic finding's fingerprint so
a changed finding never reuses a stale explanation, and records a controlled
error code/message when a generation attempt fails.

New columns are all nullable so the widening applies to any existing rows.

Revision ID: f4a5b6c7d8e9
Revises: e3f4a5b6c7d8
Create Date: 2026-09-10 01:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "f4a5b6c7d8e9"
down_revision: str | None = "e3f4a5b6c7d8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("explanations", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("finding_fingerprint", sa.String(length=64), nullable=True)
        )
        batch_op.add_column(sa.Column("payload", sa.JSON(), nullable=True))
        batch_op.add_column(
            sa.Column("error_code", sa.String(length=64), nullable=True)
        )
        batch_op.add_column(sa.Column("error_message", sa.Text(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("explanations", schema=None) as batch_op:
        batch_op.drop_column("error_message")
        batch_op.drop_column("error_code")
        batch_op.drop_column("payload")
        batch_op.drop_column("finding_fingerprint")
