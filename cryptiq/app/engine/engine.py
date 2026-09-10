"""Entry point for the deterministic analysis engine.

The engine is a pure function of a source snapshot and a rule set: no network,
no model calls, no randomness. This module currently owns the version stamps
that every later stage attaches to its output.
"""

from app.config import Settings, get_settings
from app.engine.models import EngineVersions


def engine_versions(settings: Settings | None = None) -> EngineVersions:
    """Return the version stamps for the configured parser and rule sets."""
    settings = settings or get_settings()
    return EngineVersions(
        parser_version=settings.parser_version,
        ruleset_version=settings.ruleset_version,
        pqc_ruleset_version=settings.pqc_ruleset_version,
    )
