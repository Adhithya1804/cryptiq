"""SQLAlchemy engine, session factory and declarative base.

The schema stays portable: models should use generic SQLAlchemy types so the
same metadata runs on SQLite locally and on PostgreSQL later.
"""

from sqlalchemy import Engine, create_engine
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


def get_engine(database_url: str | None = None) -> Engine:
    """Create an engine for the given URL, defaulting to the configured one."""
    url = database_url or get_settings().database_url
    return create_engine(url, future=True, **_engine_kwargs(url))


engine = get_engine()

SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
