"""Scan execution orchestrator service for Cryptiq."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, List, Optional

from cryptiq.cache.fingerprint import FingerprintEngine
from cryptiq.cache.identity import ScanCacheManager, ScanIdentity
from cryptiq.compat.interfaces import AnalysisEngine, RuleMatch, SourceProvider
from cryptiq.core.enums import (
    ConfidenceLevel,
    ErrorCode,
    RetrievalMode,
    ScanStatus,
)
from cryptiq.core.models import (
    Evidence,
    Finding,
    Scan,
)
from cryptiq.impact.analyzer import ImpactAnalyzer
from cryptiq.priority.scorer import PriorityScorer
from cryptiq.storage.repositories import FindingRepository, ScanRepository

logger = logging.getLogger("cryptiq.worker.service")


def _categorize_error(exc: Exception) -> ErrorCode:
    """Map exception to a deterministic, sanitized ErrorCode without leaking internal paths."""
    exc_name = type(exc).__name__.lower()
    msg = str(exc).lower()

    if "not found" in msg or "404" in msg:
        if "commit" in msg:
            return ErrorCode.COMMIT_NOT_FOUND
        return ErrorCode.REPOSITORY_NOT_FOUND
    if "unavailable" in msg or "network" in msg or "connection" in msg:
        return ErrorCode.REPOSITORY_UNAVAILABLE
    if "parse" in msg or "syntax" in msg or "parser" in exc_name:
        return ErrorCode.PARSER_ERROR
    if "timeout" in msg:
        return ErrorCode.SCAN_TIMEOUT
    if "persistence" in msg or "database" in msg or "sqlite" in exc_name:
        return ErrorCode.PERSISTENCE_ERROR
    return ErrorCode.ANALYSIS_ERROR


class ScanService:
    """Coordinates snapshot ingestion, cryptographic analysis, impact, priority, fingerprinting, and persistence."""

    def __init__(
        self,
        scan_repo: ScanRepository,
        finding_repo: FindingRepository,
        source_provider: SourceProvider,
        analysis_engine: AnalysisEngine,
        impact_analyzer: Optional[ImpactAnalyzer] = None,
        priority_scorer: Optional[PriorityScorer] = None,
    ):
        self.scan_repo = scan_repo
        self.finding_repo = finding_repo
        self.source_provider = source_provider
        self.analysis_engine = analysis_engine
        self.impact_analyzer = impact_analyzer or ImpactAnalyzer()
        self.priority_scorer = priority_scorer or PriorityScorer()

    def request_scan(
        self,
        provider: str,
        owner: str,
        repository: str,
        commit_sha: str,
        parser_version: str,
        ruleset_version: str,
        pqc_ruleset_version: str,
        job_repo: Optional[Any] = None,
    ) -> tuple[Scan, Optional[Any], bool]:
        """Request a scan with deterministic cache lookup before creating or running.

        Returns:
            (scan, job, is_cache_hit)
        """
        identity = ScanIdentity(
            provider=provider,
            owner=owner,
            repository=repository,
            commit_sha=commit_sha,
            parser_version=parser_version,
            ruleset_version=ruleset_version,
            pqc_ruleset_version=pqc_ruleset_version,
        )

        cached_scan = ScanCacheManager.get_cached_scan(identity, self.scan_repo)
        if cached_scan is not None:
            return cached_scan, None, True

        # Cache miss: create new Scan and ScanJob
        scan_id = str(uuid.uuid4())
        scan = Scan(
            id=scan_id,
            provider=provider,
            owner=owner,
            repository=repository,
            commit_sha=commit_sha,
            parser_version=parser_version,
            ruleset_version=ruleset_version,
            pqc_ruleset_version=pqc_ruleset_version,
            status=ScanStatus.QUEUED,
        )
        self.scan_repo.create(scan)

        job = None
        if job_repo is not None:
            from cryptiq.core.models import ScanJob
            job = ScanJob(
                id=str(uuid.uuid4()),
                scan_id=scan_id,
                status=JobStatus.QUEUED,
            )
            job_repo.create(job)

        return scan, job, False

    def execute(self, scan_id: str, job_repo: Optional[Any] = None) -> Scan:
        """Execute the full scan pipeline for a given scan ID."""
        scan = self.scan_repo.get_by_id(scan_id)
        if not scan:
            raise ValueError(f"Scan {scan_id} does not exist")

        # 1. Deterministic Scan Caching Check (Phase 11)
        identity = ScanIdentity(
            provider=scan.provider,
            owner=scan.owner,
            repository=scan.repository,
            commit_sha=scan.commit_sha,
            parser_version=scan.parser_version,
            ruleset_version=scan.ruleset_version,
            pqc_ruleset_version=scan.pqc_ruleset_version,
        )

        cached_scan = ScanCacheManager.get_cached_scan(
            identity,
            self.scan_repo,
            exclude_id=scan.id,
        )
        if cached_scan is not None and cached_scan.id != scan.id:
            # Re-use cached completed scan without creating duplicate completed record
            if job_repo is not None:
                job_repo.reassign_scan_id(scan.id, cached_scan.id)
            try:
                self.scan_repo.delete(scan.id)
            except Exception:
                pass
            return cached_scan

        # 2. Fresh Execution
        scan.status = ScanStatus.RUNNING
        scan.started_at = datetime.now(timezone.utc)
        self.scan_repo.update(scan)

        # Source ingestion
        snapshot = self.source_provider.get_snapshot(
            provider=scan.provider,
            owner=scan.owner,
            repository=scan.repository,
            commit_sha=scan.commit_sha,
        )
        scan.retrieval_mode = snapshot.retrieval_mode

        # Syntax-aware analysis
        analysis_result = self.analysis_engine.analyze(snapshot)

        # Process each cryptographic observation through Phases 9, 10, 11
        findings: List[Finding] = []
        for match in analysis_result.matches:
            fid = str(uuid.uuid4())

            # Evidence (Phases 4-8)
            evidence = Evidence(
                file_path=match.file_path,
                line_start=match.start_line,
                line_end=match.end_line,
                code_snippet=match.code_snippet,
                confidence=match.confidence,
                call_site=match.call_site,
                function_name=match.function_name,
                class_name=match.class_name,
                module_name=match.module_name,
            )

            # Phase 9: Bounded Impact Analysis
            impact = self.impact_analyzer.analyze(
                raw_finding={
                    "id": fid,
                    "algorithm": match.algorithm,
                    "api": match.api,
                    "confidence": match.confidence,
                },
                parsed_context=evidence,
            )

            # Phase 10: Deterministic Migration Review Priority
            priority = self.priority_scorer.score(
                finding=match,
                role=match.role,
                impact=impact,
            )

            # Phase 11: Finding Fingerprint
            fingerprint = FingerprintEngine.compute(
                repository=f"{scan.owner}/{scan.repository}",
                commit_sha=scan.commit_sha,
                file_path=match.file_path,
                start_line=match.start_line,
                rule_id=match.rule_id,
                algorithm=match.algorithm,
                api=match.api,
            )

            finding = Finding(
                id=fid,
                scan_id=scan.id,
                repository=f"{scan.owner}/{scan.repository}",
                commit_sha=scan.commit_sha,
                file_path=match.file_path,
                start_line=match.start_line,
                end_line=match.end_line,
                rule_id=match.rule_id,
                algorithm=match.algorithm,
                api=match.api,
                confidence=match.confidence,
                role=match.role,
                pqc_guidance=match.pqc_guidance,
                priority=priority.level,
                priority_reasons=priority.reasons,
                fingerprint=fingerprint,
                evidence=evidence,
                impact=impact,
                created_at=datetime.now(timezone.utc),
            )
            findings.append(finding)

        # 3. Transactional Result Persistence (Phase 12.8)
        self.finding_repo.save_findings_batch(scan.id, findings)

        scan.status = ScanStatus.COMPLETED
        scan.completed_at = datetime.now(timezone.utc)
        scan.file_count = analysis_result.files_analyzed
        scan.finding_count = len(findings)
        self.scan_repo.update(scan)

        return scan

    def fail(self, scan_id: str, exc: Exception) -> None:
        """Safely record a scan failure with a sanitized error code."""
        error_code = _categorize_error(exc)
        sanitized_msg = str(exc)

        # Sanitize error message to avoid leaking tokens or absolute local paths
        for sensitive_term in ["token", "secret", "password", "key", "authorization"]:
            if sensitive_term in sanitized_msg.lower():
                sanitized_msg = f"Operation failed due to {error_code.value}"
                break

        scan = self.scan_repo.get_by_id(scan_id)
        if scan:
            scan.status = ScanStatus.FAILED
            scan.completed_at = datetime.now(timezone.utc)
            scan.error_code = error_code.value
            scan.error_message = sanitized_msg
            self.scan_repo.update(scan)
