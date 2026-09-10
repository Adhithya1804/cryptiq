"""Liveness and readiness endpoints."""

import logging

from fastapi import APIRouter, Response, status
from sqlalchemy import text

from app import __version__
from app.db.database import SessionLocal
from app.schemas.health import HealthResponse, ReadinessResponse

logger = logging.getLogger(__name__)

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    """Report that the service process is up and serving requests."""
    return HealthResponse(status="ok", service="cryptiq", version=__version__)


@router.get("/health/ready", response_model=ReadinessResponse)
async def readiness(response: Response) -> ReadinessResponse:
    """Report whether the service can reach its database.

    Container orchestrators probe this to decide when to route traffic: a
    ``200`` means the process is up *and* the database answered, a ``503``
    means the process is up but not yet ready. No internal error detail is
    exposed in the body.
    """
    database_ok = True
    try:
        session = SessionLocal()
        try:
            session.execute(text("SELECT 1"))
        finally:
            session.close()
    except Exception:  # pragma: no cover - exercised only when the DB is down
        logger.exception("readiness probe: database check failed")
        database_ok = False

    if not database_ok:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    return ReadinessResponse(
        status="ok" if database_ok else "unavailable",
        service="cryptiq",
        version=__version__,
        database="ok" if database_ok else "unavailable",
    )
