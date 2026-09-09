"""Database repositories for Scans, ScanJobs, Findings, Evidence, and Impact."""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import List, Optional

from cryptiq.core.enums import (
    ConfidenceLevel,
    CryptoRole,
    ImpactNodeType,
    ImpactRelationship,
    ImpactScope,
    JobStatus,
    PriorityLevel,
    RetrievalMode,
    ScanStatus,
)
from cryptiq.core.models import (
    Evidence,
    Finding,
    ImpactEdge,
    ImpactNode,
    ImpactResult,
    Scan,
    ScanJob,
)
from cryptiq.storage.transaction import transaction


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_iso(val: Optional[str]) -> Optional[datetime]:
    if not val:
        return None
    try:
        return datetime.fromisoformat(val)
    except Exception:
        return None


class ScanRepository:
    """Data access repository for Scan snapshots."""

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def create(self, scan: Scan) -> Scan:
        created_at = scan.created_at or datetime.now(timezone.utc)
        scan.created_at = created_at
        sql = """
        INSERT INTO scans (
            id, provider, owner, repository, commit_sha,
            parser_version, ruleset_version, pqc_ruleset_version,
            status, retrieval_mode, started_at, completed_at,
            file_count, finding_count, error_code, error_message, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
        """
        self.conn.execute(
            sql,
            (
                scan.id,
                scan.provider,
                scan.owner,
                scan.repository,
                scan.commit_sha,
                scan.parser_version,
                scan.ruleset_version,
                scan.pqc_ruleset_version,
                scan.status.value,
                scan.retrieval_mode.value,
                scan.started_at.isoformat() if scan.started_at else None,
                scan.completed_at.isoformat() if scan.completed_at else None,
                scan.file_count,
                scan.finding_count,
                scan.error_code,
                scan.error_message,
                created_at.isoformat(),
            ),
        )
        return scan

    def get_by_id(self, scan_id: str) -> Optional[Scan]:
        cur = self.conn.execute("SELECT * FROM scans WHERE id = ?;", (scan_id,))
        row = cur.fetchone()
        if not row:
            return None
        return self._row_to_scan(row)

    def find_by_identity(
        self,
        provider: str,
        owner: str,
        repository: str,
        commit_sha: str,
        parser_version: str,
        ruleset_version: str,
        pqc_ruleset_version: str,
        status: Optional[ScanStatus] = None,
        exclude_id: Optional[str] = None,
    ) -> Optional[Scan]:
        """Find an existing scan by its exact 7-part deterministic identity."""
        query = """
        SELECT * FROM scans
        WHERE provider = ?
          AND owner = ?
          AND repository = ?
          AND commit_sha = ?
          AND parser_version = ?
          AND ruleset_version = ?
          AND pqc_ruleset_version = ?
        """
        params: list[Any] = [
            provider,
            owner,
            repository,
            commit_sha,
            parser_version,
            ruleset_version,
            pqc_ruleset_version,
        ]

        if status is not None:
            query += " AND status = ?"
            params.append(status.value)

        if exclude_id is not None:
            query += " AND id != ?"
            params.append(exclude_id)

        query += " ORDER BY created_at DESC LIMIT 1;"
        cur = self.conn.execute(query, tuple(params))
        row = cur.fetchone()
        if not row:
            return None
        return self._row_to_scan(row)

    def delete(self, scan_id: str) -> None:
        """Delete a scan record by ID."""
        self.conn.execute("DELETE FROM scans WHERE id = ?;", (scan_id,))

    def update(self, scan: Scan) -> None:
        sql = """
        UPDATE scans SET
            status = ?,
            retrieval_mode = ?,
            started_at = ?,
            completed_at = ?,
            file_count = ?,
            finding_count = ?,
            error_code = ?,
            error_message = ?
        WHERE id = ?;
        """
        self.conn.execute(
            sql,
            (
                scan.status.value,
                scan.retrieval_mode.value,
                scan.started_at.isoformat() if scan.started_at else None,
                scan.completed_at.isoformat() if scan.completed_at else None,
                scan.file_count,
                scan.finding_count,
                scan.error_code,
                scan.error_message,
                scan.id,
            ),
        )

    def _row_to_scan(self, row: sqlite3.Row) -> Scan:
        return Scan(
            id=row["id"],
            provider=row["provider"],
            owner=row["owner"],
            repository=row["repository"],
            commit_sha=row["commit_sha"],
            parser_version=row["parser_version"],
            ruleset_version=row["ruleset_version"],
            pqc_ruleset_version=row["pqc_ruleset_version"],
            status=ScanStatus(row["status"]),
            retrieval_mode=RetrievalMode(row["retrieval_mode"]),
            started_at=_parse_iso(row["started_at"]),
            completed_at=_parse_iso(row["completed_at"]),
            file_count=row["file_count"],
            finding_count=row["finding_count"],
            error_code=row["error_code"],
            error_message=row["error_message"],
            created_at=_parse_iso(row["created_at"]),
        )


class JobRepository:
    """Data access and concurrency-safe claiming repository for ScanJobs."""

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def create(self, job: ScanJob) -> ScanJob:
        created_at = job.created_at or datetime.now(timezone.utc)
        job.created_at = created_at
        sql = """
        INSERT INTO scan_jobs (
            id, scan_id, status, attempt_count, max_attempts,
            locked_at, locked_by, started_at, completed_at, last_error, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
        """
        self.conn.execute(
            sql,
            (
                job.id,
                job.scan_id,
                job.status.value,
                job.attempt_count,
                job.max_attempts,
                job.locked_at.isoformat() if job.locked_at else None,
                job.locked_by,
                job.started_at.isoformat() if job.started_at else None,
                job.completed_at.isoformat() if job.completed_at else None,
                job.last_error,
                created_at.isoformat(),
            ),
        )
        return job

    def get_by_id(self, job_id: str) -> Optional[ScanJob]:
        cur = self.conn.execute("SELECT * FROM scan_jobs WHERE id = ?;", (job_id,))
        row = cur.fetchone()
        if not row:
            return None
        return self._row_to_job(row)

    def get_by_scan_id(self, scan_id: str) -> Optional[ScanJob]:
        cur = self.conn.execute(
            "SELECT * FROM scan_jobs WHERE scan_id = ? ORDER BY created_at DESC LIMIT 1;",
            (scan_id,),
        )
        row = cur.fetchone()
        if not row:
            return None
        return self._row_to_job(row)

    def reassign_scan_id(self, old_scan_id: str, new_scan_id: str) -> None:
        """Reassign any jobs pointing to old_scan_id to point to new_scan_id."""
        self.conn.execute(
            "UPDATE scan_jobs SET scan_id = ? WHERE scan_id = ?;",
            (new_scan_id, old_scan_id),
        )

    def claim_next_job(
        self,
        worker_id: str,
        lock_timeout_seconds: int = 300,
    ) -> Optional[ScanJob]:
        """Atomically claim the next queued or expired job with transactional concurrency protection.

        Hides database-specific locking under the repository abstraction.
        Uses BEGIN IMMEDIATE to prevent race conditions during concurrent worker claims.
        """
        now = datetime.now(timezone.utc)
        now_str = now.isoformat()

        with transaction(self.conn, immediate=True):
            # Select next claimable job
            cur = self.conn.execute(
                """
                SELECT id FROM scan_jobs
                WHERE status = 'QUEUED'
                   OR (status = 'RUNNING' AND locked_at IS NOT NULL AND locked_at < datetime('now', ?))
                ORDER BY created_at ASC
                LIMIT 1;
                """,
                (f"-{lock_timeout_seconds} seconds",),
            )
            row = cur.fetchone()
            if not row:
                return None

            job_id = row["id"]

            # Atomically lock and advance to RUNNING
            self.conn.execute(
                """
                UPDATE scan_jobs
                SET status = 'RUNNING',
                    locked_at = ?,
                    locked_by = ?,
                    started_at = COALESCE(started_at, ?),
                    attempt_count = attempt_count + 1
                WHERE id = ? AND (status = 'QUEUED' OR status = 'RUNNING');
                """,
                (now_str, worker_id, now_str, job_id),
            )

            # Reload updated record
            cur = self.conn.execute("SELECT * FROM scan_jobs WHERE id = ?;", (job_id,))
            updated_row = cur.fetchone()
            if not updated_row:
                return None
            return self._row_to_job(updated_row)

    def mark_completed(self, job_id: str) -> None:
        now_str = _now_iso()
        self.conn.execute(
            """
            UPDATE scan_jobs
            SET status = 'COMPLETED',
                locked_at = NULL,
                locked_by = NULL,
                completed_at = ?
            WHERE id = ?;
            """,
            (now_str, job_id),
        )

    def mark_failed(self, job_id: str, error: str, retry: bool = False) -> None:
        status = JobStatus.QUEUED if retry else JobStatus.FAILED
        now_str = _now_iso()
        self.conn.execute(
            """
            UPDATE scan_jobs
            SET status = ?,
                locked_at = NULL,
                locked_by = NULL,
                last_error = ?,
                completed_at = CASE WHEN ? = 'FAILED' THEN ? ELSE completed_at END
            WHERE id = ?;
            """,
            (status.value, error, status.value, now_str, job_id),
        )

    def _row_to_job(self, row: sqlite3.Row) -> ScanJob:
        return ScanJob(
            id=row["id"],
            scan_id=row["scan_id"],
            status=JobStatus(row["status"]),
            attempt_count=row["attempt_count"],
            max_attempts=row["max_attempts"],
            locked_at=_parse_iso(row["locked_at"]),
            locked_by=row["locked_by"],
            started_at=_parse_iso(row["started_at"]),
            completed_at=_parse_iso(row["completed_at"]),
            last_error=row["last_error"],
            created_at=_parse_iso(row["created_at"]),
        )


class FindingRepository:
    """Data access repository for Findings, Evidence, and Impact graph persistence."""

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def save_findings_batch(self, scan_id: str, findings: List[Finding]) -> None:
        """Persist findings, evidence, and impact graphs inside an atomic transaction.

        Guarantees that a scan does not appear completed while findings are only partially persisted.
        """
        with transaction(self.conn, immediate=True):
            for finding in findings:
                created_at = (finding.created_at or datetime.now(timezone.utc)).isoformat()
                reasons_json = json.dumps(finding.priority_reasons)

                self.conn.execute(
                    """
                    INSERT INTO findings (
                        id, scan_id, repository, commit_sha, file_path,
                        start_line, end_line, rule_id, algorithm, api,
                        confidence, role, pqc_guidance, priority,
                        priority_reasons, fingerprint, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                    """,
                    (
                        finding.id,
                        scan_id,
                        finding.repository,
                        finding.commit_sha,
                        finding.file_path,
                        finding.start_line,
                        finding.end_line,
                        finding.rule_id,
                        finding.algorithm,
                        finding.api,
                        finding.confidence.value,
                        finding.role.value,
                        finding.pqc_guidance,
                        finding.priority.value,
                        reasons_json,
                        finding.fingerprint,
                        created_at,
                    ),
                )

                if finding.evidence:
                    ev = finding.evidence
                    ev_id = f"ev-{finding.id}"
                    self.conn.execute(
                        """
                        INSERT INTO evidence (
                            id, finding_id, file_path, line_start, line_end,
                            code_snippet, confidence, symbol, call_site,
                            function_name, class_name, module_name
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                        """,
                        (
                            ev_id,
                            finding.id,
                            ev.file_path,
                            ev.line_start,
                            ev.line_end,
                            ev.code_snippet,
                            ev.confidence.value,
                            ev.symbol,
                            ev.call_site,
                            ev.function_name,
                            ev.class_name,
                            ev.module_name,
                        ),
                    )

                if finding.impact:
                    for node in finding.impact.nodes:
                        self.conn.execute(
                            """
                            INSERT INTO impact_nodes (
                                id, finding_id, node_type, label, relationship, confidence
                            ) VALUES (?, ?, ?, ?, ?, ?);
                            """,
                            (
                                node.id,
                                finding.id,
                                node.node_type.value,
                                node.label,
                                node.relationship.value if node.relationship else None,
                                node.confidence.value,
                            ),
                        )

                    for edge in finding.impact.relationships:
                        edge_id = str(uuid.uuid4())
                        self.conn.execute(
                            """
                            INSERT INTO impact_edges (
                                id, finding_id, source_id, target_id, relationship, confidence
                            ) VALUES (?, ?, ?, ?, ?, ?);
                            """,
                            (
                                edge_id,
                                finding.id,
                                edge.source_id,
                                edge.target_id,
                                edge.relationship.value,
                                edge.confidence.value,
                            ),
                        )

    def get_findings_by_scan(self, scan_id: str) -> List[Finding]:
        cur = self.conn.execute(
            "SELECT * FROM findings WHERE scan_id = ? ORDER BY file_path, start_line;",
            (scan_id,),
        )
        findings: List[Finding] = []
        for row in cur.fetchall():
            findings.append(self._row_to_finding(row))
        return findings

    def get_by_fingerprint(self, fingerprint: str) -> List[Finding]:
        cur = self.conn.execute(
            "SELECT * FROM findings WHERE fingerprint = ? ORDER BY created_at DESC;",
            (fingerprint,),
        )
        return [self._row_to_finding(r) for r in cur.fetchall()]

    def _row_to_finding(self, row: sqlite3.Row) -> Finding:
        reasons = []
        try:
            reasons = json.loads(row["priority_reasons"])
        except Exception:
            pass

        return Finding(
            id=row["id"],
            scan_id=row["scan_id"],
            repository=row["repository"],
            commit_sha=row["commit_sha"],
            file_path=row["file_path"],
            start_line=row["start_line"],
            end_line=row["end_line"],
            rule_id=row["rule_id"],
            algorithm=row["algorithm"],
            api=row["api"],
            confidence=ConfidenceLevel(row["confidence"]),
            role=CryptoRole(row["role"]),
            pqc_guidance=row["pqc_guidance"],
            priority=PriorityLevel(row["priority"]),
            priority_reasons=reasons,
            fingerprint=row["fingerprint"],
            created_at=_parse_iso(row["created_at"]),
        )
