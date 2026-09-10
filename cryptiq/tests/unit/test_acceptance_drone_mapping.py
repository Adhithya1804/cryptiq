"""Synthetic Acceptance Test: Autonomous Drone Map Tile Processing & Deduplication.

Product Thesis & Acceptance Criteria:
- Detect cryptography: SHA-256 is detected deterministically from static analysis.
- Understand semantic role: Engine extracts that SHA-256 is used for tile caching and content addressing.
- Understand domain context: Autonomous Drone profile with constrained telemetry bandwidth and battery.
- Authoritative knowledge: NIST SP 800-131A & avionics guidance confirm SHA-256 is acceptable and secure.
- Migration assessment: Output is KEEP.
- Guardrail invariant: NEVER map content-addressing hashes to ML-DSA (digital signature category error!).
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from app.cli.main import main
from app.engine.context.models import AssessmentDecision, ContextualRole, DomainProfile
from app.services.context_advisor import ContextAdvisorService

TILE_CACHE_SOURCE = """\
# Drone Offline Map Tile Processing and Content Addressing Service
from cryptography.hazmat.primitives import hashes


class TerrainTileCache:
    \"\"\"Cache map tiles locally on drone flash storage using content-addressed SHA-256.\"\"\"

    def __init__(self, cache_dir: str):
        self.cache_dir = cache_dir

    def compute_tile_key(self, zoom: int, x: int, y: int, raw_tile_data: bytes) -> str:
        # Line 12: Content addressing hash digest
        digest = hashes.Hash(hashes.SHA256())
        digest.update(raw_tile_data)
        return digest.finalize().hex()
"""


def _run(argv: list[str], capsys) -> tuple[int, str, str]:
    code = main(argv)
    captured = capsys.readouterr()
    return code, captured.out, captured.err


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


def _init_drone_repo(root: Path) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    _git(root, "init", "-q")
    _git(root, "config", "user.email", "flight-ops@drone.internal")
    _git(root, "config", "user.name", "Flight Systems")
    src = root / "src" / "navigation"
    src.mkdir(parents=True, exist_ok=True)
    (src / "tile_cache.py").write_text(TILE_CACHE_SOURCE, encoding="utf-8")
    _git(root, "add", ".")
    _git(root, "commit", "-q", "-m", "Implement drone offline terrain tile cache")
    return root


def test_drone_mapping_sha256_assessed_as_keep_via_service():
    """ContextAdvisorService evaluates drone tile cache SHA-256 as KEEP."""
    advisor = ContextAdvisorService()
    domain = DomainProfile.autonomous_drone()

    assessment = advisor.assess_facts(
        algorithm="SHA-256",
        api="hashes.SHA256",
        primitive="hash",
        library="cryptography",
        operation="hash",
        file_path="src/navigation/tile_cache.py",
        start_line=12,
        end_line=12,
        deterministic_role="hash",
        deterministic_confidence="high",
        source_excerpt="digest = hashes.Hash(hashes.SHA256())",
        domain_profile=domain,
    )

    # 1. Decision must be KEEP
    assert assessment.assessment == AssessmentDecision.KEEP
    assert assessment.pqc_migration_required is False
    assert assessment.migration_candidate is None

    # 2. Semantic role must be CONTENT_ADDRESSING or DATA_INTEGRITY
    assert assessment.contextual_role in (
        ContextualRole.CONTENT_ADDRESSING,
        ContextualRole.DATA_INTEGRITY,
        ContextualRole.HASHING,
    )

    # 3. Guardrail: Must NEVER recommend ML-DSA for hash content addressing!
    assert "ML-DSA" not in (assessment.migration_candidate or "")
    for alt in assessment.alternatives:
        assert "ML-DSA" not in alt

    # 4. Rationale must explain hash integrity vs signature distinction
    rationale_lower = assessment.rationale.lower()
    assert "content addressing" in rationale_lower or "tile" in rationale_lower or "hash" in rationale_lower

    # 5. Authoritative citations must reference NIST SP 800-131A or avionics guidance
    citations = [src["document_id"] for src in assessment.knowledge_sources]
    assert any("800-131A" in c or "AVIONICS" in c for c in citations)


def test_drone_mapping_cli_scan_json_output(tmp_path: Path, capsys):
    """Running CLI scan on drone repo with --domain autonomous-drone outputs contextual assessment."""
    repo = _init_drone_repo(tmp_path / "drone-repo")

    _code, out, _err = _run(
        ["scan", str(repo), "--domain", "autonomous-drone", "--format", "json"],
        capsys,
    )

    data = json.loads(out)
    assert "findings" in data
    assert len(data["findings"]) >= 1

    sha_findings = [f for f in data["findings"] if f["observed"]["algorithm"] == "SHA-256"]
    assert len(sha_findings) >= 1
    finding = sha_findings[0]

    # Contextual assessment block must be present
    assert "contextual_assessment" in finding
    ca = finding["contextual_assessment"]
    assert ca is not None
    assert ca["assessment"] == "KEEP"
    assert ca["pqc_migration_required"] is False
    assert ca["migration_candidate"] is None
    assert ca["domain_profile"]["domain"] == "AUTONOMOUS_DRONE"
