"""Value objects shared across the deterministic analysis pipeline."""

from pydantic import BaseModel, ConfigDict


class EngineVersions(BaseModel):
    """Version stamps that make an analysis result reproducible.

    Every finding is produced by a specific parser and rule set. Recording the
    versions alongside a result is what lets two scans be compared, or a scan be
    invalidated when a rule set changes.
    """

    model_config = ConfigDict(frozen=True)

    parser_version: str
    ruleset_version: str
    pqc_ruleset_version: str
