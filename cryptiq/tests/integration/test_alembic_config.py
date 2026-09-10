"""The Alembic configuration is valid and its revisions form a single chain."""

from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _config() -> Config:
    return Config(str(PROJECT_ROOT / "alembic.ini"))


def test_alembic_ini_exists() -> None:
    assert (PROJECT_ROOT / "alembic.ini").is_file()


def test_script_directory_loads_with_a_single_head() -> None:
    scripts = ScriptDirectory.from_config(_config())

    assert len(scripts.get_heads()) == 1


def test_url_is_not_hard_coded_in_alembic_ini() -> None:
    assert _config().get_main_option("sqlalchemy.url") is None
