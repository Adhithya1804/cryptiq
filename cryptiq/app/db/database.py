"""SQLAlchemy engine, session factory and declarative base.

The schema stays portable: models should use generic SQLAlchemy types so the
same metadata runs on SQLite locally and on PostgreSQL later.
"""

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import get_settings


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""


def _engine_kwargs(database_url: str) -> dict[str, object]:
    if database_url.startswith("sqlite"):
        # SQLite connections are bound to the creating thread by default, which
        # breaks FastAPI's threadpool for sync endpoints and dependencies.
        return {"connect_args": {"check_same_thread": False}}
    return {"pool_pre_ping": True}


def _is_file_sqlite(url: str) -> bool:
    """True for an on-disk SQLite URL — not ``:memory:`` and not a bare URL."""
    if not url.startswith("sqlite"):
        return False
    tail = url.split("sqlite:", 1)[1].lstrip("/")
    return bool(tail) and ":memory:" not in url


def _apply_sqlite_pragmas(engine: Engine, url: str) -> None:
    """Set ``busy_timeout`` (and optionally WAL) on every file SQLite connection.

    ``busy_timeout`` turns an immediate "database is locked" into a short wait,
    which matters once the single-instance demo persists SQLite on EBS and the
    worker writes while the API reads. WAL (off by default, ``SQLITE_WAL=true``)
    additionally lets those reads run during a write. In-memory databases (the
    test suite) get no connect listener at all.
    """
    if not _is_file_sqlite(url):
        return
    settings = get_settings()
    busy_timeout = settings.sqlite_busy_timeout_ms
    use_wal = settings.sqlite_wal

    @event.listens_for(engine, "connect")
    def _set_sqlite_pragmas(dbapi_connection, _record) -> None:
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute(f"PRAGMA busy_timeout={int(busy_timeout)}")
            if use_wal:
                cursor.execute("PRAGMA journal_mode=WAL")
        finally:
            cursor.close()


def get_engine(database_url: str | None = None) -> Engine:
    """Create an engine for the given URL, defaulting to the configured one."""
    url = database_url or get_settings().database_url
    new_engine = create_engine(url, future=True, **_engine_kwargs(url))
    _apply_sqlite_pragmas(new_engine, url)
    return new_engine


engine = get_engine()

SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
