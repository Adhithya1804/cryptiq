"""scan job retry bounds and lock owner

Adds the two columns a database-backed worker needs: a per-job retry ceiling
and the identity of whichever worker holds the lock.

Revision ID: d1449ca9aa37
Revises: 42c2c7f7e9dc
Create Date: 2026-09-09 18:41:46.641261

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d1449ca9aa37"
down_revision: str | None = "42c2c7f7e9dc"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

DEFAULT_MAX_ATTEMPTS = "3"


def upgrade() -> None:
    """Add the retry ceiling and the lock owner."""
    with op.batch_alter_table("scan_jobs", schema=None) as batch_op:
        # A server default lets the column be added NOT NULL to a table that
        # already holds rows; the application supplies the value from then on.
        batch_op.add_column(
            sa.Column(
                "max_attempts",
                sa.Integer(),
                nullable=False,
                server_default=sa.text(DEFAULT_MAX_ATTEMPTS),
            )
        )
        batch_op.add_column(sa.Column("locked_by", sa.String(length=64), nullable=True))


def downgrade() -> None:
    """Drop the retry ceiling and the lock owner."""
    with op.batch_alter_table("scan_jobs", schema=None) as batch_op:
        batch_op.drop_column("locked_by")
        batch_op.drop_column("max_attempts")
