"""Aggregate router for the v1 API."""

from fastapi import APIRouter

from app.api.v1 import (
    findings,
    health,
    inspections,
    projects,
    review_items,
    review_queue,
    scans,
)

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(inspections.router)
api_router.include_router(scans.router)
api_router.include_router(findings.router)
api_router.include_router(projects.router)
api_router.include_router(review_queue.router)
api_router.include_router(review_items.router)
