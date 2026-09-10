"""Scan schemas for the domain and API boundary."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.db.models.enums import ScanStatus, SourceState


class ScanCreate(BaseModel):
    """The request to analyse a repository at an exact commit."""

    repository_id: str
    commit_sha: str = Field(min_length=7, max_length=40)
    base_commit_sha: str | None = Field(default=None, min_length=7, max_length=40)


class ScanRead(BaseModel):
    """A stored scan, including the version stamps that make it reproducible."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    repository_id: str
    commit_sha: str
    base_commit_sha: str | None
    status: ScanStatus
    source_state: SourceState
    parser_version: str
    ruleset_version: str
    pqc_ruleset_version: str
    file_count: int
    analyzed_file_count: int
    skipped_file_count: int
    finding_count: int
    started_at: datetime | None
    completed_at: datetime | None
    error_code: str | None
    error_message: str | None
    created_at: datetime
