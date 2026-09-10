"""The HTTP wire contract the React frontend consumes.

These shapes mirror ``frontend/src/types/api.ts`` exactly. The frontend
normalises enum casing and tolerates ``string | string[]`` in a few places, so
this module sends the backend's own uppercase enum tokens and lets the client
map them onto its domain vocabulary.

Nothing here recomputes analysis. Every value is copied from a persisted row
or from a serialised engine result.
"""

from __future__ import annotations

from typing import Annotated, Any

from pydantic import BaseModel, Field, StringConstraints

# A short free-text constraint token (domain name, sensitivity label, a single
# regulatory / platform / interoperability tag). Bounded so an unauthenticated
# caller cannot pad the contextual-assessment request -- every one of these
# strings is forwarded into the Gemini prompt.
_ShortTag = Annotated[str, StringConstraints(max_length=120, strip_whitespace=True)]


class ApiRepositoryRef(BaseModel):
    """A repository identity as the client renders it."""

    provider: str
    owner: str
    name: str
    url: str | None = None


class ApiLocation(BaseModel):
    """A source span."""

    file_path: str
    start_line: int
    end_line: int | None = None
    start_column: int | None = None
    end_column: int | None = None


class ApiSeverityBreakdown(BaseModel):
    """Finding counts by priority band, for one inspection."""

    critical: int = 0
    high: int = 0
    medium: int = 0
    low: int = 0


class ApiInspectionDto(BaseModel):
    """One inspection: one repository analysed at one exact commit."""

    id: str
    repository_id: str | None = None
    repository: ApiRepositoryRef
    language: str = "Python"
    commit_sha: str
    status: str
    started_at: str | None = None
    completed_at: str | None = None
    duration_ms: int | None = None
    files_analyzed: int | None = None
    findings_count: int = 0
    severity: ApiSeverityBreakdown = Field(default_factory=ApiSeverityBreakdown)
    error_code: str | None = None
    error_message: str | None = None
    # True when this scan was served from a previously completed identical
    # scan rather than freshly queued. Only ``POST /scans`` ever sets it.
    cached: bool = False


class ApiRepositoryDto(BaseModel):
    """A repository row on the Projects screen."""

    id: str
    repository: ApiRepositoryRef
    language: str = "Python"
    last_inspected_at: str | None = None
    latest_inspection_status: str | None = None
    findings_count: int | None = None


class ApiObservedBlock(BaseModel):
    """What the deterministic rules established. Every field is checkable."""

    rule_id: str
    algorithm: str
    api: str
    primitive: str
    library: str
    operation: str
    location: ApiLocation
    source_excerpt: str
    enclosing_function: str | None = None
    enclosing_class: str | None = None
    parser_version: str
    ruleset_version: str


class ApiInferenceBlock(BaseModel):
    """What the engine concluded, and how firmly."""

    role: str
    rationale: list[str]
    confidence: str
    evidence_basis: str | None = None


class ApiMigrationBlock(BaseModel):
    """The post-quantum guidance to review this finding against."""

    review_path: str
    rationale: str
    is_migration_candidate: bool
    pqc_ruleset_version: str
    current: str


class ApiImpactBlock(BaseModel):
    """The bounded, statically-observed blast radius."""

    scope: str
    node_count: int
    nodes: list[str] = Field(default_factory=list)
    relationships: list[str] = Field(default_factory=list)


class ApiPriorityBlock(BaseModel):
    """Where the finding sits in the migration review queue."""

    level: str
    score: int
    reasons: list[str] = Field(default_factory=list)


class ApiReviewBlock(BaseModel):
    """Human review state. ``null`` on a finding until a review is opened."""

    id: str
    status: str
    assigned_to: str | None = None
    note: str | None = None
    created_at: str | None = None
    updated_at: str | None = None


class ApiFindingDto(BaseModel):
    """The complete finding, grouped by how far a reviewer can trust each part."""

    id: str
    scan_id: str
    # The engine's stable, line-independent finding identity. Additive: lets a
    # client (the CLI diff, SARIF fingerprints) track a finding across commits
    # without re-deriving it.
    fingerprint: str | None = None
    repository: ApiRepositoryRef
    commit_sha: str
    language: str = "Python"
    observed: ApiObservedBlock
    inference: ApiInferenceBlock
    migration: ApiMigrationBlock
    impact: ApiImpactBlock
    priority: ApiPriorityBlock
    review: ApiReviewBlock | None = None
    ai_explanation_available: bool = False


class ApiFindingSummaryDto(BaseModel):
    """A findings-table row."""

    id: str
    scan_id: str
    algorithm: str
    api: str
    operation: str
    role: str
    confidence: str
    review_path: str
    is_migration_candidate: bool
    priority: str
    priority_score: int
    file_path: str
    start_line: int
    end_line: int | None = None
    review_status: str | None = None


class ApiReviewQueueItemDto(BaseModel):
    """A row in the Review queue."""

    review_id: str
    finding_id: str
    scan_id: str
    algorithm: str
    api: str
    role: str
    review_path: str
    priority: str
    priority_score: int
    status: str
    assigned_to: str | None = None
    note: str | None = None
    reasons: list[str] = Field(default_factory=list)
    file_path: str
    start_line: int
    updated_at: str | None = None


class ApiExplanationDto(BaseModel):
    """A backend-generated natural-language explanation of one finding.

    Additive only: every field here is explanatory prose produced *after*
    detection. Nothing in this shape can override a value in
    :class:`ApiFindingDto`.
    """

    finding_id: str
    provider: str
    model: str
    prompt_version: str
    summary: str
    why_it_matters: str = ""
    evidence_explanation: str = ""
    migration_explanation: str = ""
    impact_explanation: str = ""
    limitations: list[str] = Field(default_factory=list)
    cached: bool = False
    generated_at: str | None = None


class ApiDomainProfileDto(BaseModel):
    """Domain profile and engineering constraints.

    Client-supplied and entirely optional. Every field is length-bounded: the
    profile is forwarded verbatim into the migration-assessment prompt, and a
    distinct profile is a distinct cache key, so an unbounded profile would be
    both a prompt-padding and a cache-busting lever on an unauthenticated
    endpoint.
    """

    model_config = {"extra": "ignore"}

    domain: Annotated[str, StringConstraints(max_length=64, strip_whitespace=True)] = (
        "GENERAL_SOFTWARE"
    )
    latency_sensitivity: _ShortTag = "UNKNOWN"
    bandwidth_constraint: _ShortTag = "UNKNOWN"
    compute_constraint: _ShortTag = "UNKNOWN"
    memory_constraint: _ShortTag = "UNKNOWN"
    battery_constraint: _ShortTag = "UNKNOWN"
    offline_operation: bool | None = None
    signature_frequency: _ShortTag | None = None
    verification_frequency: _ShortTag | None = None
    payload_size_sensitivity: _ShortTag = "UNKNOWN"
    data_longevity: _ShortTag | None = None
    regulatory_requirements: list[_ShortTag] = Field(default_factory=list, max_length=20)
    platform_constraints: list[_ShortTag] = Field(default_factory=list, max_length=20)
    interoperability_constraints: list[_ShortTag] = Field(
        default_factory=list, max_length=20
    )


class ApiKnowledgeSourceDto(BaseModel):
    """An authoritative standards chunk citation."""

    document_id: str
    chunk_id: str
    title: str
    publisher: str
    url: str
    section: str
    version: str
    content: str
    relevance_score: float = 0.0


class ApiContextualAssessmentDto(BaseModel):
    """The context-aware post-quantum migration evaluation of a finding."""

    id: str | None = None
    finding_id: str
    fingerprint: str
    assessment: str
    confidence: str
    contextual_role: str
    rationale: str
    pqc_migration_required: bool
    migration_candidate: str | None = None
    alternatives: list[str] = Field(default_factory=list)
    engineering_tradeoffs: list[str] = Field(default_factory=list)
    required_context: list[str] = Field(default_factory=list)
    evidence_interpretation: str = ""
    knowledge_sources: list[dict[str, Any]] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    domain_profile: dict[str, Any] = Field(default_factory=dict)
    generated_by: str = "heuristic_advisor"
    model: str | None = None
    prompt_version: str | None = None
    cached: bool = False
    created_at: str | None = None


class ApiListEnvelope[T](BaseModel):
    """The list wrapper every collection endpoint returns."""

    items: list[T]
    total: int | None = None
    next_cursor: str | None = None


class ApiPageEnvelope[T](BaseModel):
    """One page of a collection, with the metadata the pager UI needs.

    ``pages`` is the total page count for the current ``page_size`` (at least 1,
    even when there are no items).
    """

    items: list[T]
    total: int
    page: int
    page_size: int
    pages: int


# --------------------------------------------------------------- requests ---


class CreateInspectionRequest(BaseModel):
    """The Inspect form submission."""

    repository_url: str = Field(min_length=1)
    commit_sha: str = Field(min_length=7, max_length=40)


class SubmitReviewRequest(BaseModel):
    """A disposition recorded on a finding."""

    status: str
    note: str | None = None


class UpdateReviewItemRequest(BaseModel):
    """A PATCH to one review item.

    Every field is optional. A field left out of the request body is left
    unchanged; a field sent as ``null`` clears it (``assigned_to``, ``note``).
    The route inspects ``model_fields_set`` to tell the two apart.
    """

    status: str | None = None
    assigned_to: str | None = None
    note: str | None = None


class CreateMigrationAssessmentRequest(BaseModel):
    """Request payload for generating a contextual migration assessment."""

    domain_profile: ApiDomainProfileDto | None = None
