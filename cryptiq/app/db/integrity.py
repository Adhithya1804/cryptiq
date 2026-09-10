"""Domain integrity rules enforced at flush time.

Cryptiq's core rule is that a finding is only a fact if the source span that
justifies it is stored with it. The database can enforce that evidence points
at a real finding, but not that a finding has evidence, so the check runs on
the session flush that would otherwise write a bare finding.
"""

from sqlalchemy import event
from sqlalchemy.orm import Session

from app.db.models.finding import Finding
from app.errors import CryptiqError


class MissingEvidenceError(CryptiqError):
    """Raised when a finding would be persisted without its evidence."""

    status_code = 500
    code = "missing_evidence"


@event.listens_for(Session, "before_flush")
def _require_evidence(session: Session, _flush_context: object, _instances: object) -> None:
    for instance in session.new:
        if isinstance(instance, Finding) and instance.evidence is None:
            raise MissingEvidenceError(
                f"Finding {instance.fingerprint!r} cannot be persisted without evidence."
            )
