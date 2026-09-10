"""ORM models.

Alembic imports this module so autogenerate sees every table, so every new
model must be imported here. Importing the package also registers the domain
integrity rules.
"""

from app.db.database import Base
from app.db.models.audit_event import AuditEvent
from app.db.models.evidence import Evidence
from app.db.models.explanation import Explanation
from app.db.models.finding import Finding
from app.db.models.impact_node import ImpactNode
from app.db.models.migration_assessment import MigrationAssessmentRecord
from app.db.models.repository import Repository
from app.db.models.review_item import ReviewItem
from app.db.models.scan import Scan
from app.db.models.scan_job import ScanJob

from app.db import integrity  # noqa: F401  isort:skip  registers the flush-time rules

__all__ = [
    "AuditEvent",
    "Base",
    "Evidence",
    "Explanation",
    "Finding",
    "ImpactNode",
    "MigrationAssessmentRecord",
    "Repository",
    "ReviewItem",
    "Scan",
    "ScanJob",
]
