"""The deterministic pipeline, from a source snapshot to finished observations.

Everything that touches the source happens here, while the snapshot is still
on disk. What comes back holds no file handles and no paths into the snapshot,
so it stays valid after ``ingest_commit`` has cleaned up.
"""

import logging
from dataclasses import dataclass
from pathlib import Path

from app.engine.evidence import Evidence
from app.engine.evidence import extract as extract_evidence
from app.engine.fingerprints import finding_fingerprint
from app.engine.impact import ImpactResult
from app.engine.impact import analyze as analyze_impact
from app.engine.ingestion import IngestionResult, RepositoryReference
from app.engine.parser import parse_all
from app.engine.pqc import PqcAssessment
from app.engine.pqc import map_review_path as map_pqc
from app.engine.priority import PriorityResult
from app.engine.priority import score as score_priority
from app.engine.roles import RoleAssessment
from app.engine.roles import classify as classify_role
from app.engine.rules import CryptoRule, RuleMatch, evaluate_files

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AnalyzedFinding:
    """One observation with everything the deterministic stages established.

    ``match`` and ``evidence`` are observed: a reviewer can check both against
    the file. ``role`` is inferred from them. ``pqc``, ``impact`` and
    ``priority`` are derived from the inference. Nothing after the rule stage
    ever changes an observed fact.
    """

    match: RuleMatch
    evidence: Evidence
    role: RoleAssessment
    pqc: PqcAssessment
    impact: ImpactResult
    priority: PriorityResult
    fingerprint: str

    @property
    def sort_key(self) -> tuple[str, int, int, str, str]:
        """The order findings are reported in."""
        return self.match.sort_key


@dataclass(frozen=True)
class AnalysisResult:
    """The outcome of analysing one snapshot."""

    repository: RepositoryReference
    commit_sha: str
    content_hash: str
    findings: tuple[AnalyzedFinding, ...]
    parsed_files: int
    failed_files: int
    total_files: int
    analyzed_files: int
    skipped_files: int


def analyze_snapshot(
    ingestion: IngestionResult,
    root: Path,
    rules: list[CryptoRule] | None = None,
) -> AnalysisResult:
    """Run the whole deterministic pipeline over an extracted snapshot.

    ``root`` must still exist: evidence is read from it. A finding whose source
    cannot be read is dropped rather than stored without evidence, because a
    finding without evidence is not a fact Cryptiq will assert.
    """
    parsed = parse_all(root, ingestion.discovered_files)
    modules = {file.path: file.module_path for file in parsed}
    matches = evaluate_files(parsed, rules)

    findings = [
        finding
        for match in matches
        if (finding := _build(match, modules, root, ingestion)) is not None
    ]
    findings.sort(key=lambda finding: finding.sort_key)

    failed = sum(1 for file in parsed if not file.parsed)
    logger.info(
        "analysed %s at %s: %d findings from %d files",
        ingestion.repository.slug,
        ingestion.commit_sha,
        len(findings),
        len(parsed),
    )
    return AnalysisResult(
        repository=ingestion.repository,
        commit_sha=ingestion.commit_sha,
        content_hash=ingestion.content_hash,
        findings=tuple(findings),
        parsed_files=len(parsed) - failed,
        failed_files=failed,
        total_files=ingestion.total_files,
        analyzed_files=ingestion.analyzed_files,
        skipped_files=ingestion.skipped_files,
    )


def _build(
    match: RuleMatch,
    modules: dict[str, str | None],
    root: Path,
    ingestion: IngestionResult,
) -> AnalyzedFinding | None:
    evidence = extract_evidence(match, root, ingestion.commit_sha)
    if evidence is None:
        logger.warning("dropping a match whose source could not be read")
        return None

    role = classify_role(match)
    impact = analyze_impact(match, modules.get(match.file_path))
    return AnalyzedFinding(
        match=match,
        evidence=evidence,
        role=role,
        pqc=map_pqc(match.algorithm, role.role),
        impact=impact,
        priority=score_priority(match, impact, role.role),
        fingerprint=finding_fingerprint(
            repository=_repository_key(ingestion.repository),
            file_path=match.file_path,
            rule_id=match.rule_id,
            algorithm=match.algorithm,
            api=match.api,
            operation=match.operation.value,
            enclosing_function=match.enclosing_function,
            enclosing_class=match.enclosing_class,
        ),
    )


def _repository_key(repository: RepositoryReference) -> str:
    """The repository part of a fingerprint, stable across providers."""
    return f"{repository.provider}/{repository.slug}"
