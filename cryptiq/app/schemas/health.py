"""Schemas for the health endpoints."""

from pydantic import BaseModel


class HealthResponse(BaseModel):
    """Machine-readable liveness report."""

    status: str
    service: str
    version: str


class ReadinessResponse(BaseModel):
    """Machine-readable readiness report, including database reachability."""

    status: str
    service: str
    version: str
    database: str
