"""Regression: submitting a brand-new repository twice at once must not 500.

``_upsert_repository`` does a lookup and then an insert. Two concurrent
requests for a repository that has never been seen can both miss the lookup
and both attempt the insert; the unique constraint on
``(provider, owner, name)`` lets one win. The loser must recover by re-reading
the winner's row, not propagate an ``IntegrityError`` (which the API renders
as a 500).
"""

from __future__ import annotations

from unittest import mock

from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session, sessionmaker

from app.db.models.repository import Repository
from app.services import scans

_URL = "https://github.com/pallets/click"


def test_upsert_repository_recovers_when_another_request_won_the_insert(
    engine: Engine, session: Session
) -> None:
    # The racing winner: a different session commits the identity first.
    other = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)()
    other.add(
        Repository(
            provider="github",
            owner="pallets",
            name="click",
            canonical_url=_URL,
        )
    )
    other.commit()
    other.close()

    # Force our session's first lookup to miss, so the insert path runs and
    # collides with the row the winner already committed.
    real_scalars = session.scalars
    calls = {"n": 0}

    class _Empty:
        def first(self) -> None:
            return None

    def flaky_scalars(statement, *args, **kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            return _Empty()
        return real_scalars(statement, *args, **kwargs)

    with mock.patch.object(session, "scalars", flaky_scalars):
        repo = scans._upsert_repository(session, _URL)

    assert (repo.provider, repo.owner, repo.name) == ("github", "pallets", "click")
    # The session is still usable and no duplicate row was written.
    session.commit()
    count = session.scalar(
        select(func.count()).select_from(Repository).where(Repository.name == "click")
    )
    assert count == 1
