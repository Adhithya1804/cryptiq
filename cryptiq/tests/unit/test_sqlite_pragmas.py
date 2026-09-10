"""File-backed SQLite gets ``busy_timeout`` + WAL; ``:memory:`` is left alone."""

from __future__ import annotations

from sqlalchemy import text

from app.config import get_settings
from app.db.database import _is_file_sqlite, get_engine


def test_is_file_sqlite_classification() -> None:
    assert _is_file_sqlite("sqlite:////data/cryptiq.db") is True
    assert _is_file_sqlite("sqlite:///./cryptiq.db") is True
    assert _is_file_sqlite("sqlite://") is False
    assert _is_file_sqlite("sqlite:///:memory:") is False
    assert _is_file_sqlite("postgresql+psycopg://u:p@db/cryptiq") is False


def test_file_sqlite_sets_busy_timeout_and_keeps_default_journal(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.setenv("SQLITE_BUSY_TIMEOUT_MS", "4200")
    monkeypatch.delenv("SQLITE_WAL", raising=False)
    get_settings.cache_clear()
    try:
        engine = get_engine(f"sqlite:///{tmp_path / 'pragma.db'}")
        with engine.connect() as conn:
            assert conn.execute(text("PRAGMA busy_timeout")).scalar() == 4200
            # WAL is off by default: journal stays the SQLite default (delete).
            assert conn.execute(text("PRAGMA journal_mode")).scalar().lower() == "delete"
        engine.dispose()
    finally:
        get_settings.cache_clear()


def test_file_sqlite_enables_wal_when_opted_in(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("SQLITE_WAL", "true")
    get_settings.cache_clear()
    try:
        engine = get_engine(f"sqlite:///{tmp_path / 'wal.db'}")
        with engine.connect() as conn:
            assert conn.execute(text("PRAGMA journal_mode")).scalar().lower() == "wal"
        engine.dispose()
    finally:
        get_settings.cache_clear()


def test_memory_sqlite_engine_is_untouched() -> None:
    engine = get_engine("sqlite://")
    with engine.connect() as conn:
        # No connect listener is attached for an in-memory DB, so WAL is never
        # forced: an in-memory database cannot use WAL and reports "memory".
        assert conn.execute(text("PRAGMA journal_mode")).scalar().lower() == "memory"
    engine.dispose()
