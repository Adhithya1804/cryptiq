"""The engine reports the configured version stamps and fingerprints stably."""

import pytest

from app.config import Settings
from app.engine import engine_versions
from app.engine.fingerprints import fingerprint


def test_versions_come_from_settings() -> None:
    settings = Settings(_env_file=None, ruleset_version="9.9.9")

    versions = engine_versions(settings)

    assert versions.parser_version == "python-ast-1"
    assert versions.ruleset_version == "9.9.9"


def test_fingerprint_is_deterministic() -> None:
    assert fingerprint("a", "b") == fingerprint("a", "b")


def test_fingerprint_separates_parts() -> None:
    assert fingerprint("ab", "c") != fingerprint("a", "bc")


def test_fingerprint_rejects_empty_input() -> None:
    with pytest.raises(ValueError):
        fingerprint()
