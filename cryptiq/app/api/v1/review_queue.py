"""The global review queue: every finding awaiting a disposition.

Without query parameters the endpoint returns the whole queue (the shape the
first frontend integration expects). Pass ``page`` to get one server-filtered,
server-ordered page instead; ``total`` always reports the full match count.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query

from app.dependencies import DbSession
from app.schemas.api import ApiListEnvelope, ApiReviewQueueItemDto
from app.services import scans
from app.services.serialize import review_queue_item_dto

router = APIRouter(tags=["review"])


@router.get("/review-queue", response_model=ApiListEnvelope[ApiReviewQueueItemDto])
def get_review_queue(
    session: DbSession,
    page: Annotated[int | None, Query(ge=1)] = None,
    page_size: Annotated[
        int, Query(ge=1, le=scans.MAX_PAGE_SIZE)
    ] = scans.DEFAULT_PAGE_SIZE,
    priority: str | None = None,
    algorithm: str | None = None,
    role: str | None = None,
    status: str | None = None,
) -> ApiListEnvelope[ApiReviewQueueItemDto]:
    if page is None and priority is None and algorithm is None and role is None and status is None:
        pairs = scans.list_review_queue(session)
        items = [review_queue_item_dto(review, finding) for review, finding in pairs]
        return ApiListEnvelope(items=items, total=len(items))

    pairs, total = scans.list_review_queue_page(
        session,
        page=page or 1,
        page_size=page_size,
        priority=priority,
        algorithm=algorithm,
        role=role,
        review_status=status,
    )
    items = [review_queue_item_dto(review, finding) for review, finding in pairs]
    return ApiListEnvelope(items=items, total=total)
