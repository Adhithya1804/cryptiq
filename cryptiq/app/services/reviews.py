"""Recording a human disposition on a finding.

The four dispositions the Finding Detail screen offers -- Keep Open, In
Review, Resolved, Accept Risk, False Positive -- are the review workflow. A
finding that has never been touched has an OPEN review item (migration
candidates get one when the scan completes); the first disposition on any
other finding creates the item.

Transitions are checked so the UI cannot drive the row into a state the
workflow does not allow.
"""

from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from app.db.models.enums import ReviewStatus
from app.db.models.finding import Finding
from app.db.models.review_item import ReviewItem
from app.errors import CryptiqError, NotFoundError, ValidationError
from app.services.scans import get_finding

logger = logging.getLogger(__name__)

#: Sentinel for "this PATCH field was not sent" — distinct from an explicit
#: ``null``, which clears the column.
UNSET: object = object()

# REVIEWED is a legacy alias; anything arriving as REVIEWED is treated as
# RESOLVED for both storage and transition checks.
_ALIASES = {ReviewStatus.REVIEWED: ReviewStatus.RESOLVED}

_CLOSED = frozenset(
    {ReviewStatus.RESOLVED, ReviewStatus.ACCEPTED_RISK, ReviewStatus.FALSE_POSITIVE}
)
_OPEN_STATES = frozenset({ReviewStatus.OPEN, ReviewStatus.IN_REVIEW})

# From an open state a reviewer may pick up the finding or close it; from a
# closed state they may re-open it or change the disposition. Re-selecting the
# current state is always allowed (idempotent PATCH-style POST).
LEGAL_REVIEW_TRANSITIONS: frozenset[tuple[ReviewStatus, ReviewStatus]] = frozenset(
    {(src, dst) for src in _OPEN_STATES for dst in _OPEN_STATES | _CLOSED}
    | {(src, dst) for src in _CLOSED for dst in _OPEN_STATES | _CLOSED}
)


class InvalidReviewTransitionError(CryptiqError):
    """Raised when a disposition change is not permitted by the workflow."""

    status_code = 409
    code = "INVALID_REVIEW_TRANSITION"


def parse_status(raw: str) -> ReviewStatus:
    """Turn a wire token into a stored status, applying the legacy alias."""
    try:
        status = ReviewStatus(raw.strip().upper())
    except ValueError as exc:
        raise ValidationError(f"{raw!r} is not a review status.") from exc
    return _ALIASES.get(status, status)


def _current_or_new(session: Session, finding: Finding) -> ReviewItem:
    if finding.review_items:
        return max(finding.review_items, key=lambda item: item.created_at)
    review = ReviewItem(finding_id=finding.id, status=ReviewStatus.OPEN)
    session.add(review)
    session.flush()
    return review


def record_disposition(
    session: Session,
    finding_id: str,
    raw_status: str,
    note: str | None = None,
) -> ReviewItem:
    """Apply a disposition to a finding's review item and return it."""
    target = parse_status(raw_status)
    finding = get_finding(session, finding_id)
    review = _current_or_new(session, finding)

    current = _ALIASES.get(review.status, review.status)
    if current != target and (current, target) not in LEGAL_REVIEW_TRANSITIONS:
        raise InvalidReviewTransitionError(
            f"A review cannot move from {current.value} to {target.value}."
        )

    review.status = target
    if note is not None:
        review.note = note.strip() or None
    session.commit()
    session.refresh(review)
    logger.info("finding %s review -> %s", finding_id, target.value)
    return review


def get_review_item(session: Session, review_id: str) -> ReviewItem:
    review = session.get(ReviewItem, review_id)
    if review is None:
        raise NotFoundError(f"No review item with id {review_id!r}.")
    return review


def _check_transition(current: ReviewStatus, target: ReviewStatus) -> None:
    current = _ALIASES.get(current, current)
    if current != target and (current, target) not in LEGAL_REVIEW_TRANSITIONS:
        raise InvalidReviewTransitionError(
            f"A review cannot move from {current.value} to {target.value}."
        )


def update_review_item(
    session: Session,
    review_id: str,
    *,
    raw_status: str | None = None,
    assigned_to: str | None | object = UNSET,
    note: str | None | object = UNSET,
) -> ReviewItem:
    """Apply a PATCH to a review item, keyed by the review id.

    ``assigned_to`` / ``note`` left as ``UNSET`` are untouched; passed as
    ``None`` they are cleared. An illegal status change raises
    :class:`InvalidReviewTransitionError` (HTTP 409).
    """
    review = get_review_item(session, review_id)

    if raw_status is not None:
        target = parse_status(raw_status)
        _check_transition(review.status, target)
        review.status = target

    if assigned_to is not UNSET:
        value = assigned_to.strip() if isinstance(assigned_to, str) else None
        review.assigned_to = value or None

    if note is not UNSET:
        value = note.strip() if isinstance(note, str) else None
        review.note = value or None

    session.commit()
    session.refresh(review)
    logger.info("review item %s -> %s", review_id, review.status.value)
    return review
