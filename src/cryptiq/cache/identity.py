"""Deterministic scan identity and caching lookup for Cryptiq."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from cryptiq.core.enums import RetrievalMode, ScanStatus
from cryptiq.core.models import Scan


@dataclass(frozen=True)
class ScanIdentity:
    """Canonical 7-part identity that uniquely defines a deterministic scan."""
    provider: str
    owner: str
    repository: str
    commit_sha: str
    parser_version: str
    ruleset_version: str
    pqc_ruleset_version: str

    def canonical_key(self) -> str:
        """Normalized string representation of scan identity."""
        return (
            f"{self.provider.strip().lower()}:"
            f"{self.owner.strip().lower()}:"
            f"{self.repository.strip().lower()}@"
            f"{self.commit_sha.strip().lower()}#"
            f"{self.parser_version.strip()}#"
            f"{self.ruleset_version.strip()}#"
            f"{self.pqc_ruleset_version.strip()}"
        )


class ScanCacheManager:
    """Manages cache lookups for previously completed scans."""

    @staticmethod
    def get_cached_scan(
        identity: ScanIdentity,
        scan_repository: Any,
        exclude_id: Optional[str] = None,
    ) -> Optional[Scan]:
        """Look up an existing COMPLETED scan matching the exact 7-part identity.

        Returns:
            The completed Scan marked with retrieval_mode=CACHED_REAL,
            or None if no completed scan matches.
        """
        existing = scan_repository.find_by_identity(
            provider=identity.provider,
            owner=identity.owner,
            repository=identity.repository,
            commit_sha=identity.commit_sha,
            parser_version=identity.parser_version,
            ruleset_version=identity.ruleset_version,
            pqc_ruleset_version=identity.pqc_ruleset_version,
            status=ScanStatus.COMPLETED,
            exclude_id=exclude_id,
        )

        if existing is None:
            return None

        # Only strictly COMPLETED scans qualify as cache hits
        if existing.status != ScanStatus.COMPLETED:
            return None

        # Mark source state as CACHED_REAL as mandated by specification
        existing.retrieval_mode = RetrievalMode.CACHED_REAL
        return existing
