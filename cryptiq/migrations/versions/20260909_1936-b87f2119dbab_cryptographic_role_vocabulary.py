"""cryptographic role vocabulary and enum check constraints

Two changes to the same set of tables, done together because both rewrite them.

First, the role vocabulary becomes the one the classifier produces:
DIGITAL_SIGNATURE, KEY_ESTABLISHMENT, SYMMETRIC_ENCRYPTION, HASH, PROTOCOL,
UNKNOWN. No findings are persisted yet, so no rows need translating; were there
any, SIGNATURE would become DIGITAL_SIGNATURE, KEY_EXCHANGE would become
KEY_ESTABLISHMENT and ENCRYPTION would become SYMMETRIC_ENCRYPTION.

Second, every enum column gains the CHECK constraint it was documented to have.
SQLAlchemy defaults ``create_constraint`` to False, so the earlier schema
enforced these values in Python only and the database would have accepted any
string written outside the ORM.

Revision ID: b87f2119dbab
Revises: d1449ca9aa37
Create Date: 2026-09-09 19:36:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b87f2119dbab"
down_revision: str | None = "d1449ca9aa37"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

OLD_ROLES = (
    "SIGNATURE",
    "KEY_EXCHANGE",
    "ENCRYPTION",
    "HASH",
    "KEY_DERIVATION",
    "RANDOMNESS",
    "CERTIFICATE",
    "UNKNOWN",
)
NEW_ROLES = (
    "DIGITAL_SIGNATURE",
    "KEY_ESTABLISHMENT",
    "SYMMETRIC_ENCRYPTION",
    "HASH",
    "PROTOCOL",
    "UNKNOWN",
)

LIFECYCLE = ("QUEUED", "RUNNING", "COMPLETED", "FAILED", "CANCELLED")

# Every enum column, as (table, column, constraint name, values). The role
# column is handled separately because its values change.
ENUM_COLUMNS: tuple[tuple[str, str, str, tuple[str, ...]], ...] = (
    ("scans", "status", "scan_status", LIFECYCLE),
    ("scans", "source_state", "source_state", ("LIVE", "CACHED_REAL", "UNAVAILABLE")),
    ("scan_jobs", "status", "scan_job_status", LIFECYCLE),
    ("findings", "confidence", "confidence", ("HIGH", "MEDIUM", "LOW")),
    (
        "findings",
        "priority",
        "review_priority",
        ("CRITICAL", "HIGH", "MEDIUM", "LOW", "INFORMATIONAL"),
    ),
    ("findings", "status", "finding_status", ("ACTIVE", "RESOLVED", "SUPPRESSED")),
    (
        "impact_nodes",
        "node_type",
        "impact_node_type",
        ("ALGORITHM", "API", "FUNCTION", "CLASS", "MODULE", "FILE"),
    ),
    (
        "impact_nodes",
        "relationship",
        "impact_relationship",
        ("USES", "CALLS", "DEFINED_IN", "CONTAINS", "IMPORTS"),
    ),
    ("impact_nodes", "confidence", "confidence", ("HIGH", "MEDIUM", "LOW")),
    ("review_items", "status", "review_status", ("OPEN", "IN_REVIEW", "REVIEWED")),
    ("explanations", "status", "explanation_status", ("PENDING", "COMPLETED", "FAILED")),
    (
        "audit_events",
        "event_type",
        "audit_event_type",
        (
            "SCAN_CREATED",
            "SCAN_STARTED",
            "SCAN_COMPLETED",
            "SCAN_FAILED",
            "FINDING_CREATED",
            "REVIEW_STARTED",
            "REVIEW_COMPLETED",
            "EXPLANATION_REQUESTED",
            "EXPLANATION_COMPLETED",
        ),
    ),
)

TABLES = ("scans", "scan_jobs", "findings", "impact_nodes", "review_items",
          "explanations", "audit_events")


def _enum(values: tuple[str, ...], name: str, *, constrained: bool) -> sa.Enum:
    return sa.Enum(
        *values,
        name=name,
        native_enum=False,
        create_constraint=constrained,
        length=32,
    )


def _apply(*, constrained: bool, roles: tuple[str, ...], drop_existing: bool) -> None:
    """Rewrite every enum column, with or without its check constraint.

    A constraint already on the table has to be dropped inside the same batch
    block before the replacement is added: batch mode rebuilds the table from
    the reflected schema, so anything left there is carried across.
    """
    by_table: dict[str, list[tuple[str, str, tuple[str, ...]]]] = {table: [] for table in TABLES}
    for table, column, name, values in ENUM_COLUMNS:
        by_table[table].append((column, name, values))
    by_table["findings"].append(("role", "cryptographic_role", roles))

    for table in TABLES:
        with op.batch_alter_table(table, schema=None) as batch_op:
            if drop_existing:
                for _, name, _ in _unique_constraints(by_table[table]):
                    batch_op.drop_constraint(name, type_="check")
            for column, name, values in by_table[table]:
                batch_op.alter_column(
                    column,
                    existing_type=sa.String(length=32),
                    type_=_enum(values, name, constrained=constrained),
                    existing_nullable=False,
                )


def _unique_constraints(
    entries: list[tuple[str, str, tuple[str, ...]]],
) -> list[tuple[str, str, tuple[str, ...]]]:
    """Return one entry per constraint name; two columns may share one."""
    seen: set[str] = set()
    unique = []
    for column, name, values in entries:
        if name not in seen:
            seen.add(name)
            unique.append((column, name, values))
    return unique


def upgrade() -> None:
    """Adopt the classifier's roles and constrain every enum column."""
    _apply(constrained=True, roles=NEW_ROLES, drop_existing=False)


def downgrade() -> None:
    """Restore the placeholder roles.

    Each constraint is dropped before the column is rewritten, so the table
    goes back to the plain VARCHAR columns the previous revision left.
    """
    _apply(constrained=False, roles=OLD_ROLES, drop_existing=True)
