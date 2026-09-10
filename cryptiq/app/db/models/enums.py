"""Controlled vocabularies persisted by the domain models.

Every value is stored as its own name, so the database rows stay readable and
the columns render as VARCHAR with a CHECK constraint on both SQLite and
PostgreSQL. Adding a member requires a migration that widens the constraint.
"""

from enum import StrEnum

from sqlalchemy import Enum as SAEnum


class ScanStatus(StrEnum):
    """Lifecycle of a scan."""

    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class SourceState(StrEnum):
    """Where the analysed source snapshot came from."""

    LIVE = "LIVE"
    CACHED_REAL = "CACHED_REAL"
    UNAVAILABLE = "UNAVAILABLE"


class ScanJobStatus(StrEnum):
    """Lifecycle of the unit of work that executes a scan."""

    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class CryptographicRole(StrEnum):
    """What a detected construct does cryptographically.

    The values match ``app.engine.roles.CryptographicRole``, which is the
    vocabulary the classifier produces. A role is an inference, so a stored
    finding keeps it apart from the observed algorithm and API.
    """

    DIGITAL_SIGNATURE = "DIGITAL_SIGNATURE"
    KEY_ESTABLISHMENT = "KEY_ESTABLISHMENT"
    SYMMETRIC_ENCRYPTION = "SYMMETRIC_ENCRYPTION"
    HASH = "HASH"
    PROTOCOL = "PROTOCOL"
    UNKNOWN = "UNKNOWN"


class Confidence(StrEnum):
    """How certain the deterministic rule is about a match."""

    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class ReviewPriority(StrEnum):
    """Migration review priority assigned by the priority stage."""

    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    INFORMATIONAL = "INFORMATIONAL"


class FindingStatus(StrEnum):
    """Lifecycle of a finding across scans.

    This is not the review workflow; ReviewItem owns that.
    """

    ACTIVE = "ACTIVE"
    RESOLVED = "RESOLVED"
    SUPPRESSED = "SUPPRESSED"


class ImpactNodeType(StrEnum):
    """Kind of program element a finding touches."""

    ALGORITHM = "ALGORITHM"
    API = "API"
    FUNCTION = "FUNCTION"
    CLASS = "CLASS"
    MODULE = "MODULE"
    FILE = "FILE"


class ImpactRelationship(StrEnum):
    """How an impact node relates to the finding."""

    USES = "USES"
    CALLS = "CALLS"
    DEFINED_IN = "DEFINED_IN"
    CONTAINS = "CONTAINS"
    IMPORTS = "IMPORTS"


class ReviewStatus(StrEnum):
    """Human review workflow state.

    The four dispositions the Finding Detail screen offers are first-class
    members: a reviewer moves a finding to IN_REVIEW and then closes it as
    RESOLVED, ACCEPTED_RISK or FALSE_POSITIVE. ``REVIEWED`` is retained as a
    legacy alias for RESOLVED so rows written before the vocabulary widened
    still validate; nothing produces it now.
    """

    OPEN = "OPEN"
    IN_REVIEW = "IN_REVIEW"
    RESOLVED = "RESOLVED"
    ACCEPTED_RISK = "ACCEPTED_RISK"
    FALSE_POSITIVE = "FALSE_POSITIVE"
    REVIEWED = "REVIEWED"


class ExplanationStatus(StrEnum):
    """State of a generated explanation."""

    PENDING = "PENDING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class AuditEventType(StrEnum):
    """Recorded transitions in the pipeline."""

    SCAN_CREATED = "SCAN_CREATED"
    SCAN_STARTED = "SCAN_STARTED"
    SCAN_COMPLETED = "SCAN_COMPLETED"
    SCAN_FAILED = "SCAN_FAILED"
    FINDING_CREATED = "FINDING_CREATED"
    REVIEW_STARTED = "REVIEW_STARTED"
    REVIEW_COMPLETED = "REVIEW_COMPLETED"
    EXPLANATION_REQUESTED = "EXPLANATION_REQUESTED"
    EXPLANATION_COMPLETED = "EXPLANATION_COMPLETED"
    MIGRATION_ASSESSMENT_REQUESTED = "MIGRATION_ASSESSMENT_REQUESTED"
    MIGRATION_ASSESSMENT_COMPLETED = "MIGRATION_ASSESSMENT_COMPLETED"


def enum_column(enum_class: type[StrEnum], constraint_name: str) -> SAEnum:
    """Return a portable VARCHAR-backed enum type with a named CHECK constraint.

    Native database enums are avoided: PostgreSQL would need a CREATE TYPE and
    SQLite has none, so a named check constraint keeps one schema for both.
    ``create_constraint`` is explicit because SQLAlchemy defaults it to False,
    which would leave the values enforced only in Python.
    """
    return SAEnum(
        enum_class,
        native_enum=False,
        create_constraint=True,
        length=32,
        validate_strings=True,
        name=constraint_name,
    )
