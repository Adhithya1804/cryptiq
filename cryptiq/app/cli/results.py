"""The common CLI-facing result model.

Local scans run the deterministic engine in-process and hand back
:class:`~app.engine.pipeline.AnalyzedFinding` objects; remote scans return the
``ApiFindingDto`` JSON the FastAPI backend serves. Both are normalised into one
:class:`CliFinding` here so the rest of the CLI -- the human tables, the JSON
writer and the SARIF emitter -- never has to know which path a result came
from.

Nothing in this module analyses anything. Every field is copied from a value a
deterministic stage already established (locally) or from a field the API
already sent (remotely). A value that is genuinely unavailable is ``None`` and
is rendered as ``N/A``; it is never invented.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.engine import engine_versions
from app.engine.pipeline import AnalyzedFinding

# The four priority bands, ranked. Used for deterministic ordering and for the
# ``--fail-on`` threshold. Bands the engine never emits are still ranked so the
# CLI keeps working if they ever appear.
PRIORITY_RANK = {
    "CRITICAL": 4,
    "HIGH": 3,
    "MEDIUM": 2,
    "LOW": 1,
    "INFORMATIONAL": 0,
}


def _rank(level: str | None) -> int:
    return PRIORITY_RANK.get((level or "").strip().upper(), -1)


@dataclass(frozen=True)
class CliFinding:
    """One finding, flattened, provider-independent.

    ``finding_id`` and the ``review_*`` fields are populated only for remote
    results: a local scan has no database, so there is no persisted id and no
    review lifecycle. Those fields are ``None`` locally and render as ``N/A``.
    """

    fingerprint: str | None
    finding_id: str | None = None
    scan_id: str | None = None

    # -- observed (checkable against the file) -----------------------------
    rule_id: str | None = None
    algorithm: str | None = None
    api: str | None = None
    primitive: str | None = None
    library: str | None = None
    operation: str | None = None
    file_path: str | None = None
    start_line: int | None = None
    end_line: int | None = None
    start_column: int | None = None
    end_column: int | None = None
    source_excerpt: str | None = None
    enclosing_function: str | None = None
    enclosing_class: str | None = None
    parser_version: str | None = None
    ruleset_version: str | None = None

    # -- inference -------------------------------------------------------
    role: str | None = None
    confidence: str | None = None
    evidence_basis: str | None = None
    role_rationale: list[str] = field(default_factory=list)

    # -- migration review ------------------------------------------------
    review_path: str | None = None
    migration_rationale: str | None = None
    is_migration_candidate: bool | None = None
    migration_current: str | None = None
    pqc_ruleset_version: str | None = None

    # -- impact --------------------------------------------------------
    impact_scope: str | None = None
    impact_node_count: int | None = None
    impact_nodes: list[str] = field(default_factory=list)
    impact_relationships: list[str] = field(default_factory=list)

    # -- priority -----------------------------------------------------
    priority_level: str | None = None
    priority_score: int | None = None
    priority_reasons: list[str] = field(default_factory=list)

    # -- review (remote only) --------------------------------------------
    review_status: str | None = None
    review_assignee: str | None = None
    review_note: str | None = None
    review_updated_at: str | None = None

    # -- context-aware migration advisor ---------------------------------
    contextual_assessment: dict[str, Any] | None = None

    # ------------------------------------------------------------------ #
    # ordering
    # ------------------------------------------------------------------ #

    @property
    def sort_key(self) -> tuple:
        """Deterministic order: file, then line, then a stable tie-break.

        Never depends on a machine path, a timestamp or a hash iteration
        order, so repeated scans of one repository state emit findings in one
        fixed order.
        """
        return (
            self.file_path or "",
            self.start_line or 0,
            self.start_column or 0,
            self.rule_id or "",
            self.api or "",
            self.operation or "",
            self.fingerprint or "",
        )

    # ------------------------------------------------------------------ #
    # constructors
    # ------------------------------------------------------------------ #

    @classmethod
    def from_analyzed(
        cls,
        analyzed: AnalyzedFinding,
        *,
        contextual_assessment: dict[str, Any] | None = None,
    ) -> CliFinding:
        """Build from an in-process engine result (local mode)."""
        match = analyzed.match
        location = match.location
        evidence = analyzed.evidence
        role = analyzed.role
        pqc = analyzed.pqc
        impact = analyzed.impact
        priority = analyzed.priority
        return cls(
            fingerprint=analyzed.fingerprint,
            finding_id=None,
            scan_id=None,
            rule_id=match.rule_id,
            algorithm=match.algorithm,
            api=match.api,
            primitive=match.primitive,
            library=match.library,
            operation=match.operation.value,
            file_path=match.file_path,
            start_line=location.start_line,
            end_line=location.end_line,
            start_column=location.start_column,
            end_column=location.end_column,
            source_excerpt=evidence.source_excerpt,
            enclosing_function=match.enclosing_function,
            enclosing_class=match.enclosing_class,
            parser_version=evidence.parser_version,
            ruleset_version=evidence.ruleset_version,
            role=role.role.value,
            confidence=match.confidence.value,
            evidence_basis=match.evidence_basis.value,
            role_rationale=[role.rationale] if role.rationale else [],
            review_path=pqc.review_path.value,
            migration_rationale=pqc.rationale,
            is_migration_candidate=pqc.is_migration_candidate,
            migration_current=match.algorithm,
            pqc_ruleset_version=engine_versions().pqc_ruleset_version,
            impact_scope=impact.scope.value,
            impact_node_count=impact.node_count,
            impact_nodes=[node.label for node in impact.nodes],
            impact_relationships=[
                node.relationship.value
                for node in impact.nodes
                if node.relationship is not None
            ],
            priority_level=priority.level.value,
            priority_score=priority.score,
            priority_reasons=list(priority.reasons),
            contextual_assessment=contextual_assessment,
        )

    @classmethod
    def from_finding_dto(cls, dto: dict[str, Any]) -> CliFinding:
        """Build from a remote ``GET /findings/{id}`` payload (full detail)."""
        observed = dto.get("observed") or {}
        location = observed.get("location") or {}
        inference = dto.get("inference") or {}
        migration = dto.get("migration") or {}
        impact = dto.get("impact") or {}
        priority = dto.get("priority") or {}
        review = dto.get("review") or {}
        return cls(
            fingerprint=dto.get("fingerprint"),
            finding_id=dto.get("id"),
            scan_id=dto.get("scan_id"),
            rule_id=observed.get("rule_id"),
            algorithm=observed.get("algorithm"),
            api=observed.get("api"),
            primitive=observed.get("primitive"),
            library=observed.get("library"),
            operation=observed.get("operation"),
            file_path=location.get("file_path"),
            start_line=location.get("start_line"),
            end_line=location.get("end_line"),
            start_column=location.get("start_column"),
            end_column=location.get("end_column"),
            source_excerpt=observed.get("source_excerpt"),
            enclosing_function=observed.get("enclosing_function"),
            enclosing_class=observed.get("enclosing_class"),
            parser_version=observed.get("parser_version"),
            ruleset_version=observed.get("ruleset_version"),
            role=inference.get("role"),
            confidence=inference.get("confidence"),
            evidence_basis=inference.get("evidence_basis"),
            role_rationale=list(inference.get("rationale") or []),
            review_path=migration.get("review_path"),
            migration_rationale=migration.get("rationale"),
            is_migration_candidate=migration.get("is_migration_candidate"),
            migration_current=migration.get("current"),
            pqc_ruleset_version=migration.get("pqc_ruleset_version"),
            impact_scope=impact.get("scope"),
            impact_node_count=impact.get("node_count"),
            impact_nodes=list(impact.get("nodes") or []),
            impact_relationships=list(impact.get("relationships") or []),
            priority_level=priority.get("level"),
            priority_score=priority.get("score"),
            priority_reasons=list(priority.get("reasons") or []),
            review_status=review.get("status"),
            review_assignee=review.get("assigned_to"),
            review_note=review.get("note"),
            review_updated_at=review.get("updated_at"),
        )

    @classmethod
    def from_summary_dto(cls, dto: dict[str, Any]) -> CliFinding:
        """Build from a remote findings-table / review-queue summary row.

        A summary row has no evidence, impact graph or rationale; only the
        fields the table shows are populated. The rest stay ``None``.
        """
        return cls(
            fingerprint=dto.get("fingerprint"),
            finding_id=dto.get("id") or dto.get("finding_id"),
            scan_id=dto.get("scan_id"),
            rule_id=dto.get("rule_id"),
            algorithm=dto.get("algorithm"),
            api=dto.get("api"),
            operation=dto.get("operation"),
            file_path=dto.get("file_path"),
            start_line=dto.get("start_line"),
            end_line=dto.get("end_line"),
            role=dto.get("role"),
            confidence=dto.get("confidence"),
            review_path=dto.get("review_path"),
            is_migration_candidate=dto.get("is_migration_candidate"),
            priority_level=dto.get("priority"),
            priority_score=dto.get("priority_score"),
            priority_reasons=list(dto.get("reasons") or []),
            review_status=dto.get("review_status") or dto.get("status"),
            review_assignee=dto.get("assigned_to"),
            review_note=dto.get("note"),
            review_updated_at=dto.get("updated_at"),
            contextual_assessment=dto.get("contextual_assessment"),
        )

    # ------------------------------------------------------------------ #
    # serialisation
    # ------------------------------------------------------------------ #

    def to_dict(self) -> dict[str, Any]:
        """Return the grouped, machine-readable shape.

        The five deterministic blocks the reviewer works through, in order,
        plus the review block. Unavailable scalars are ``null`` (never a
        fabricated value); the human renderer shows ``N/A`` for them.
        """
        payload = {
            "id": self.finding_id,
            "fingerprint": self.fingerprint,
            "scan_id": self.scan_id,
            "observed": {
                "rule": self.rule_id,
                "algorithm": self.algorithm,
                "api": self.api,
                "primitive": self.primitive,
                "library": self.library,
                "operation": self.operation,
                "file": self.file_path,
                "start_line": self.start_line,
                "end_line": self.end_line,
                "start_column": self.start_column,
                "end_column": self.end_column,
                "evidence": self.source_excerpt,
                "enclosing_function": self.enclosing_function,
                "enclosing_class": self.enclosing_class,
                "parser_version": self.parser_version,
                "ruleset_version": self.ruleset_version,
            },
            "inference": {
                "role": self.role,
                "confidence": self.confidence,
                "basis": self.evidence_basis,
                "rationale": list(self.role_rationale),
            },
            "migration_review": {
                "pqc_family": self.review_path,
                "candidate": self.is_migration_candidate,
                "standards": self.migration_rationale,
                "current": self.migration_current,
                "pqc_ruleset_version": self.pqc_ruleset_version,
            },
            "impact": {
                "scope": self.impact_scope,
                "node_count": self.impact_node_count,
                "nodes": list(self.impact_nodes),
                "relationships": list(self.impact_relationships),
            },
            "priority": {
                "level": self.priority_level,
                "score": self.priority_score,
                "reasons": list(self.priority_reasons),
            },
            "review": {
                "status": self.review_status,
                "assignee": self.review_assignee,
                "note": self.review_note,
                "updated_at": self.review_updated_at,
            },
        }
        if self.contextual_assessment is not None:
            payload["contextual_assessment"] = self.contextual_assessment
        return payload

    @property
    def priority_rank(self) -> int:
        """Numeric rank of the priority band, for thresholds and ordering."""
        return _rank(self.priority_level)
