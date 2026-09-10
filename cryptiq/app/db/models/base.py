"""Primary key and timestamp mixins shared by the domain models."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

ID_LENGTH = 36


def new_id() -> str:
    """Return a fresh identifier.

    Identifiers are UUID4 strings rather than integers so records can be
    created by a worker without a round trip, and rather than a native UUID
    column so the same schema runs on SQLite and PostgreSQL.
    """
    return str(uuid.uuid4())


def utcnow() -> datetime:
    """Return the current time as a timezone-aware UTC value."""
    return datetime.now(UTC)


class UUIDPrimaryKeyMixin:
    """String UUID primary key."""

    id: Mapped[str] = mapped_column(String(ID_LENGTH), primary_key=True, default=new_id)


class CreatedAtMixin:
    """Creation timestamp, set by the application in UTC."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )


class UpdatedAtMixin:
    """Last-modified timestamp, refreshed on every update."""

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )
