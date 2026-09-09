"""Deterministic finding fingerprint engine for Cryptiq."""

from __future__ import annotations

import hashlib
from typing import Any, Optional


def _extract(obj: Any, key: str, default: Any = None) -> Any:
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


class FingerprintEngine:
    """Generates stable, canonical sha256 fingerprints for cryptographic findings."""

    @staticmethod
    def canonical_string(
        repository: str,
        commit_sha: str,
        file_path: str,
        start_line: int,
        rule_id: str,
        algorithm: str,
        api: str,
    ) -> str:
        """Construct a stable canonical string representation for finding identity.

        Does not rely on str(dict) to guarantee cross-platform and runtime stability.
        """
        clean_repo = str(repository or "").strip().lower()
        clean_commit = str(commit_sha or "").strip().lower()
        clean_file = str(file_path or "").strip()
        clean_line = str(int(start_line))
        clean_rule = str(rule_id or "").strip()
        clean_algo = str(algorithm or "").strip().upper()
        clean_api = str(api or "").strip()

        return (
            f"repository:{clean_repo}|"
            f"commit_sha:{clean_commit}|"
            f"file_path:{clean_file}|"
            f"start_line:{clean_line}|"
            f"rule_id:{clean_rule}|"
            f"algorithm:{clean_algo}|"
            f"api:{clean_api}"
        )

    @classmethod
    def compute(
        cls,
        repository: str,
        commit_sha: str,
        file_path: str,
        start_line: int,
        rule_id: str,
        algorithm: str,
        api: str,
    ) -> str:
        """Compute sha256 fingerprint from canonical identity fields."""
        canonical = cls.canonical_string(
            repository=repository,
            commit_sha=commit_sha,
            file_path=file_path,
            start_line=start_line,
            rule_id=rule_id,
            algorithm=algorithm,
            api=api,
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    @classmethod
    def fingerprint_finding(cls, finding: Any) -> str:
        """Extract canonical identity fields from finding object or dict and return fingerprint."""
        repo = _extract(finding, "repository", "")
        commit = _extract(finding, "commit_sha", "")
        file_path = _extract(finding, "file_path", "") or _extract(finding, "file", "")
        line = _extract(finding, "start_line", 0) or _extract(finding, "line_start", 0)
        rule = _extract(finding, "rule_id", "") or _extract(finding, "rule", "")
        algo = _extract(finding, "algorithm", "")
        api = _extract(finding, "api", "") or _extract(finding, "api_or_symbol", "")

        return cls.compute(
            repository=repo,
            commit_sha=commit,
            file_path=file_path,
            start_line=int(line),
            rule_id=rule,
            algorithm=algo,
            api=api,
        )
