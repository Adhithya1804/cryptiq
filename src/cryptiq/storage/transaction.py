"""Transaction helpers for database operations."""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from typing import Generator


@contextmanager
def transaction(conn: sqlite3.Connection, immediate: bool = True) -> Generator[sqlite3.Connection, None, None]:
    """Provide a transactional boundary with explicit BEGIN/COMMIT/ROLLBACK.

    Uses BEGIN IMMEDIATE by default to acquire a write lock immediately in SQLite,
    preventing SQLITE_BUSY deadlocks during concurrent claims.
    """
    begin_stmt = "BEGIN IMMEDIATE;" if immediate else "BEGIN;"
    conn.execute(begin_stmt)
    try:
        yield conn
        conn.execute("COMMIT;")
    except Exception:
        try:
            conn.execute("ROLLBACK;")
        except Exception:
            pass
        raise
