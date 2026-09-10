"""Context Engine package.

Extracts static repository context, domain profiles, and enforces semantic guardrails.
"""

from app.engine.context.extractor import extract_context
from app.engine.context.guardrails import enforce_guardrails
from app.engine.context.models import (
    AssessmentConfidence,
    AssessmentDecision,
    ConstraintLevel,
    ContextualAssessment,
    ContextualRole,
    DomainProfile,
    ExtractedContext,
)

__all__ = [
    "AssessmentConfidence",
    "AssessmentDecision",
    "ConstraintLevel",
    "ContextualAssessment",
    "ContextualRole",
    "DomainProfile",
    "ExtractedContext",
    "enforce_guardrails",
    "extract_context",
]
