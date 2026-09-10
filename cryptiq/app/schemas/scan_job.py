"""Scan job schemas for the domain and API boundary."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.db.models.enums import ScanJobStatus


class ScanJobRead(BaseModel):
    """A stored execution attempt for a scan."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    scan_id: str
    status: ScanJobStatus
    attempt_count: int
    locked_at: datetime | None
    started_at: datetime | None
    completed_at: datetime | None
    last_error: str | None
    created_at: datetime
