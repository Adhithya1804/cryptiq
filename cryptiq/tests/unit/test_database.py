"""The engine and session factory are usable."""

from sqlalchemy import text

from app.db.database import Base, SessionLocal, get_engine
from app.dependencies import get_db


def test_session_can_be_created_and_queried() -> None:
    with SessionLocal() as session:
        assert session.execute(text("select 1")).scalar_one() == 1


def test_get_db_yields_a_session_and_closes_it() -> None:
    generator = get_db()
    session = next(generator)

    assert session.execute(text("select 1")).scalar_one() == 1

    generator.close()


def test_declarative_base_exposes_metadata() -> None:
    assert Base.metadata is not None


def test_engine_accepts_an_explicit_url() -> None:
    engine = get_engine("sqlite:///:memory:")

    with engine.connect() as connection:
        assert connection.execute(text("select 1")).scalar_one() == 1

    engine.dispose()
