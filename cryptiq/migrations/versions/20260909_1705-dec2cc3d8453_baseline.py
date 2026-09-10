"""baseline

Empty first revision. It anchors the migration chain so later revisions have a
stable down_revision, and it lets `alembic upgrade head` create the version
table on a fresh database. Domain tables arrive in later revisions.

Revision ID: dec2cc3d8453
Revises:
Create Date: 2026-09-09 17:05:11.899234

"""

from collections.abc import Sequence

revision: str = "dec2cc3d8453"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """No schema changes."""


def downgrade() -> None:
    """No schema changes."""
