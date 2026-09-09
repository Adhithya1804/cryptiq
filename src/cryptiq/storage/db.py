"""Database connection and schema management for Cryptiq."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Optional, Union

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS scans (
    id TEXT PRIMARY KEY,
    provider TEXT NOT NULL,
    owner TEXT NOT NULL,
    repository TEXT NOT NULL,
    commit_sha TEXT NOT NULL,
    parser_version TEXT NOT NULL,
    ruleset_version TEXT NOT NULL,
    pqc_ruleset_version TEXT NOT NULL,
    status TEXT NOT NULL,
    retrieval_mode TEXT NOT NULL,
    started_at TEXT,
    completed_at TEXT,
    file_count INTEGER DEFAULT 0,
    finding_count INTEGER DEFAULT 0,
    error_code TEXT,
    error_message TEXT,
    created_at TEXT NOT NULL
);

-- Unique index guaranteeing logical uniqueness for completed scans
CREATE UNIQUE INDEX IF NOT EXISTS idx_scans_completed_identity
ON scans (
    provider,
    owner,
    repository,
    commit_sha,
    parser_version,
    ruleset_version,
    pqc_ruleset_version
) WHERE status = 'COMPLETED';

CREATE INDEX IF NOT EXISTS idx_scans_status
ON scans (status);

CREATE TABLE IF NOT EXISTS scan_jobs (
    id TEXT PRIMARY KEY,
    scan_id TEXT NOT NULL,
    status TEXT NOT NULL,
    attempt_count INTEGER DEFAULT 0,
    max_attempts INTEGER DEFAULT 3,
    locked_at TEXT,
    locked_by TEXT,
    started_at TEXT,
    completed_at TEXT,
    last_error TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY(scan_id) REFERENCES scans(id)
);

CREATE INDEX IF NOT EXISTS idx_jobs_status_locked
ON scan_jobs (status, locked_at);

CREATE TABLE IF NOT EXISTS findings (
    id TEXT PRIMARY KEY,
    scan_id TEXT NOT NULL,
    repository TEXT NOT NULL,
    commit_sha TEXT NOT NULL,
    file_path TEXT NOT NULL,
    start_line INTEGER NOT NULL,
    end_line INTEGER NOT NULL,
    rule_id TEXT NOT NULL,
    algorithm TEXT NOT NULL,
    api TEXT NOT NULL,
    confidence TEXT NOT NULL,
    role TEXT NOT NULL,
    pqc_guidance TEXT NOT NULL,
    priority TEXT NOT NULL,
    priority_reasons TEXT NOT NULL,
    fingerprint TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY(scan_id) REFERENCES scans(id)
);

CREATE INDEX IF NOT EXISTS idx_findings_fingerprint
ON findings (fingerprint);

CREATE INDEX IF NOT EXISTS idx_findings_scan_id
ON findings (scan_id);

CREATE TABLE IF NOT EXISTS evidence (
    id TEXT PRIMARY KEY,
    finding_id TEXT NOT NULL,
    file_path TEXT NOT NULL,
    line_start INTEGER NOT NULL,
    line_end INTEGER NOT NULL,
    code_snippet TEXT NOT NULL,
    confidence TEXT NOT NULL,
    symbol TEXT,
    call_site TEXT,
    function_name TEXT,
    class_name TEXT,
    module_name TEXT,
    FOREIGN KEY(finding_id) REFERENCES findings(id)
);

CREATE TABLE IF NOT EXISTS impact_nodes (
    id TEXT PRIMARY KEY,
    finding_id TEXT NOT NULL,
    node_type TEXT NOT NULL,
    label TEXT NOT NULL,
    relationship TEXT,
    confidence TEXT NOT NULL,
    FOREIGN KEY(finding_id) REFERENCES findings(id)
);

CREATE TABLE IF NOT EXISTS impact_edges (
    id TEXT PRIMARY KEY,
    finding_id TEXT NOT NULL,
    source_id TEXT NOT NULL,
    target_id TEXT NOT NULL,
    relationship TEXT NOT NULL,
    confidence TEXT NOT NULL,
    FOREIGN KEY(finding_id) REFERENCES findings(id)
);
"""


class Database:
    """Database connection and initialization wrapper."""

    def __init__(self, db_path: Union[str, Path] = ":memory:"):
        self.db_path = str(db_path)
        self._connection: Optional[sqlite3.Connection] = None

    def connect(self) -> sqlite3.Connection:
        """Create or return an active connection configured for concurrency."""
        if self._connection is None or self.db_path == ":memory:":
            conn = sqlite3.connect(
                self.db_path,
                check_same_thread=False,
                timeout=30.0,
                isolation_level=None,  # Autocommit mode by default; manual transactions via BEGIN
            )
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA foreign_keys = ON;")
            conn.execute("PRAGMA journal_mode = WAL;")
            conn.execute("PRAGMA busy_timeout = 30000;")
            if self.db_path == ":memory:":
                self._connection = conn
            return conn
        return self._connection

    def init_schema(self, conn: Optional[sqlite3.Connection] = None) -> None:
        """Execute the DDL schema to set up all tables and indexes."""
        close_after = False
        if conn is None:
            conn = self.connect()
            if self.db_path != ":memory:":
                close_after = True

        conn.executescript(SCHEMA_SQL)
        if close_after:
            conn.close()

    def close(self) -> None:
        """Close connection if held."""
        if self._connection is not None:
            self._connection.close()
            self._connection = None
