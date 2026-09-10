"""create migration_assessments table for context-aware migration advisor

Revision ID: b6c7d8e9f0a1
Revises: a5b6c7d8e9f0
Create Date: 2026-09-10 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b6c7d8e9f0a1"
down_revision: str | None = "a5b6c7d8e9f0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "migration_assessments",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.Column("finding_id", sa.String(length=36), nullable=False),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("model", sa.String(length=128), nullable=True),
        sa.Column("prompt_version", sa.String(length=64), nullable=False),
        sa.Column("knowledge_version", sa.String(length=64), nullable=False),
        sa.Column("finding_fingerprint", sa.String(length=64), nullable=True),
        sa.Column("domain", sa.String(length=64), nullable=False),
        sa.Column("domain_profile_hash", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("decision", sa.String(length=32), nullable=True),
        sa.Column("confidence", sa.String(length=32), nullable=True),
        sa.Column("contextual_role", sa.String(length=64), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=True),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["finding_id"], ["findings.id"], name="fk_migration_assessments_finding_id", ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name="pk_migration_assessments"),
    )
    with op.batch_alter_table("migration_assessments", schema=None) as batch_op:
        batch_op.create_index("ix_migration_assessments_finding_id", ["finding_id"], unique=False)
        batch_op.create_index("ix_migration_assessments_finding_fingerprint", ["finding_fingerprint"], unique=False)
        batch_op.create_index("ix_migration_assessments_domain_profile_hash", ["domain_profile_hash"], unique=False)
        batch_op.create_index(
            "ix_migration_assessments_cache_key",
            ["finding_fingerprint", "domain_profile_hash", "knowledge_version", "prompt_version", "model"],
            unique=False,
        )


def downgrade() -> None:
    with op.batch_alter_table("migration_assessments", schema=None) as batch_op:
        batch_op.drop_index("ix_migration_assessments_cache_key")
        batch_op.drop_index("ix_migration_assessments_domain_profile_hash")
        batch_op.drop_index("ix_migration_assessments_finding_fingerprint")
        batch_op.drop_index("ix_migration_assessments_finding_id")
    op.drop_table("migration_assessments")
