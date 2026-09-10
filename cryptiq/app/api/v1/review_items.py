"""Review-item endpoint — update one queue entry by its own id.

``PATCH /api/v1/review-items/{review_id}`` is the canonical write the Review
screen uses. It differs from ``POST /findings/{id}/review`` only in being keyed
by the review row rather than the finding, and in accepting ``assigned_to``.
Both share the transition rules in :mod:`app.services.reviews`.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.dependencies import DbSession
from app.schemas.api import ApiReviewBlock, UpdateReviewItemRequest
from app.services.reviews import UNSET, update_review_item
from app.services.serialize import review_block

router = APIRouter(prefix="/review-items", tags=["review"])


@router.patch("/{review_id}", response_model=ApiReviewBlock)
def patch_review_item(
    review_id: str, body: UpdateReviewItemRequest, session: DbSession
) -> ApiReviewBlock:
    sent = body.model_fields_set
    review = update_review_item(
        session,
        review_id,
        raw_status=body.status,
        assigned_to=body.assigned_to if "assigned_to" in sent else UNSET,
        note=body.note if "note" in sent else UNSET,
    )
    return review_block(review)
