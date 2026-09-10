"""The schema stays portable between SQLite and PostgreSQL."""

from sqlalchemy import Enum

import app.db.models  # noqa: F401  registers every table
from app.db.database import Base

EXPECTED_TABLES = {
    "repositories",
    "scans",
    "scan_jobs",
    "findings",
    "evidence",
    "impact_nodes",
    "review_items",
    "explanations",
    "audit_events",
}


def test_metadata_holds_the_nine_domain_tables() -> None:
    assert EXPECTED_TABLES <= set(Base.metadata.tables)


def test_no_column_uses_a_dialect_specific_type() -> None:
    offenders = [
        f"{table.name}.{column.name}: {type(column.type).__module__}"
        for table in Base.metadata.tables.values()
        for column in table.columns
        if "dialects" in type(column.type).__module__
    ]

    assert offenders == []


def test_enums_are_stored_as_checked_strings() -> None:
    enum_columns = [
        column
        for table in Base.metadata.tables.values()
        for column in table.columns
        if isinstance(column.type, Enum)
    ]

    assert enum_columns
    # Native enums would need a CREATE TYPE on PostgreSQL and do not exist on
    # SQLite, so every enum must render as VARCHAR with a check constraint.
    assert all(column.type.native_enum is False for column in enum_columns)
    assert all(column.type.name is not None for column in enum_columns)
