"""The domain migration applies, reverses and re-applies on a clean database."""

import sqlite3
from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config

PROJECT_ROOT = Path(__file__).resolve().parents[2]
BASELINE_REVISION = "dec2cc3d8453"
DOMAIN_REVISION = "42c2c7f7e9dc"

DOMAIN_TABLES = {
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


@pytest.fixture
def alembic_config(tmp_path: Path) -> Iterator[Config]:
    """Return an Alembic config pointed at a throwaway SQLite file."""
    config = Config(str(PROJECT_ROOT / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", f"sqlite:///{tmp_path / 'migration-test.db'}")
    config.attributes["db_path"] = tmp_path / "migration-test.db"
    yield config


def _table_names(config: Config) -> set[str]:
    connection = sqlite3.connect(config.attributes["db_path"])
    try:
        rows = connection.execute("select name from sqlite_master where type='table'")
        return {row[0] for row in rows}
    finally:
        connection.close()


def _index_names(config: Config, table: str) -> set[str]:
    connection = sqlite3.connect(config.attributes["db_path"])
    try:
        rows = connection.execute(f"pragma index_list('{table}')")
        return {row[1] for row in rows}
    finally:
        connection.close()


def _column_names(config: Config, table: str) -> set[str]:
    connection = sqlite3.connect(config.attributes["db_path"])
    try:
        return {row[1] for row in connection.execute(f"pragma table_info('{table}')")}
    finally:
        connection.close()


def _foreign_keys(config: Config, table: str) -> set[tuple[str, str, str]]:
    connection = sqlite3.connect(config.attributes["db_path"])
    try:
        rows = connection.execute(f"pragma foreign_key_list('{table}')")
        return {(row[2], row[3], row[6]) for row in rows}
    finally:
        connection.close()


def test_upgrade_creates_every_domain_table(alembic_config: Config) -> None:
    command.upgrade(alembic_config, "head")

    assert DOMAIN_TABLES <= _table_names(alembic_config)


def test_downgrade_then_upgrade_restores_the_schema(alembic_config: Config) -> None:
    command.upgrade(alembic_config, "head")
    command.downgrade(alembic_config, BASELINE_REVISION)

    assert not DOMAIN_TABLES & _table_names(alembic_config)

    command.upgrade(alembic_config, "head")

    assert DOMAIN_TABLES <= _table_names(alembic_config)


def test_the_scan_job_worker_columns_are_added(alembic_config: Config) -> None:
    command.upgrade(alembic_config, "head")

    assert {"max_attempts", "locked_by"} <= _column_names(alembic_config, "scan_jobs")

    command.downgrade(alembic_config, DOMAIN_REVISION)

    assert not {"max_attempts", "locked_by"} & _column_names(alembic_config, "scan_jobs")


def test_expected_indexes_exist(alembic_config: Config) -> None:
    command.upgrade(alembic_config, "head")

    assert {"ix_scans_repository_id", "ix_scans_commit_sha", "ix_scans_status"} <= _index_names(
        alembic_config, "scans"
    )
    assert {
        "ix_findings_scan_id",
        "ix_findings_fingerprint",
        "ix_findings_priority",
        "ix_findings_role",
    } <= _index_names(alembic_config, "findings")
    assert {"ix_scan_jobs_scan_id", "ix_scan_jobs_status"} <= _index_names(
        alembic_config, "scan_jobs"
    )
    assert {"ix_review_items_finding_id", "ix_review_items_status"} <= _index_names(
        alembic_config, "review_items"
    )
    assert {"ix_audit_events_scan_id", "ix_audit_events_finding_id"} <= _index_names(
        alembic_config, "audit_events"
    )
    assert "ix_evidence_finding_id" in _index_names(alembic_config, "evidence")


def test_foreign_keys_carry_the_expected_delete_rules(alembic_config: Config) -> None:
    command.upgrade(alembic_config, "head")

    assert ("repositories", "repository_id", "CASCADE") in _foreign_keys(alembic_config, "scans")
    assert ("scans", "scan_id", "CASCADE") in _foreign_keys(alembic_config, "findings")
    assert ("scans", "scan_id", "CASCADE") in _foreign_keys(alembic_config, "scan_jobs")
    assert ("findings", "finding_id", "CASCADE") in _foreign_keys(alembic_config, "evidence")
    assert _foreign_keys(alembic_config, "audit_events") == {
        ("findings", "finding_id", "SET NULL"),
        ("scans", "scan_id", "SET NULL"),
    }
