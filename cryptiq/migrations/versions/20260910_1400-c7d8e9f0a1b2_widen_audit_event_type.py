"""widen audit_event_type vocabulary to include migration assessment events

Revision ID: c7d8e9f0a1b2
Revises: b6c7d8e9f0a1
Create Date: 2026-09-10 14:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c7d8e9f0a1b2"
down_revision: str | None = "b6c7d8e9f0a1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

OLD_EVENT_TYPES = (
    "SCAN_CREATED",
    "SCAN_STARTED",
    "SCAN_COMPLETED",
    "SCAN_FAILED",
    "FINDING_CREATED",
    "REVIEW_STARTED",
    "REVIEW_COMPLETED",
    "EXPLANATION_REQUESTED",
    "EXPLANATION_COMPLETED",
)

NEW_EVENT_TYPES = (
    "SCAN_CREATED",
    "SCAN_STARTED",
    "SCAN_COMPLETED",
    "SCAN_FAILED",
    "FINDING_CREATED",
    "REVIEW_STARTED",
    "REVIEW_COMPLETED",
    "EXPLANATION_REQUESTED",
    "EXPLANATION_COMPLETED",
    "MIGRATION_ASSESSMENT_REQUESTED",
    "MIGRATION_ASSESSMENT_COMPLETED",
)


def _enum(values: tuple[str, ...]) -> sa.Enum:
    return sa.Enum(
        *values,
        name="audit_event_type",
        native_enum=False,
        create_constraint=True,
        length=32,
    )


def _rewrite(values: tuple[str, ...]) -> None:
    with op.batch_alter_table("audit_events", schema=None) as batch_op:
        batch_op.drop_constraint("audit_event_type", type_="check")
        batch_op.alter_column(
            "event_type",
            existing_type=sa.String(length=32),
            type_=_enum(values),
            existing_nullable=False,
        )


def upgrade() -> None:
    _rewrite(NEW_EVENT_TYPES)


def downgrade() -> None:
    _rewrite(OLD_EVENT_TYPES)
