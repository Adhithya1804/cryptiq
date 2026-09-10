"""Synthetic Acceptance Test: Key Establishment (Diffie-Hellman / ECDH / X25519).

Product Thesis & Acceptance Criteria:
- Detect cryptography: Key exchange primitive (ECDH / X25519) is detected.
- Understand semantic role: Engine classifies as KEY_ESTABLISHMENT.
- Authoritative knowledge: NIST FIPS 203 (ML-KEM Standard).
- Migration assessment: Output is MIGRATE with candidate ML-KEM-768.
- Guardrail invariant: NEVER map key establishment to ML-DSA or SLH-DSA (signature category error!).
- Rationale: Accurately explains that public-key key exchange must migrate to a post-quantum
  Key Encapsulation Mechanism (KEM) rather than a signature scheme.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from app.cli.main import main
from app.engine.context.models import AssessmentDecision, DomainProfile
from app.services.context_advisor import ContextAdvisorService

KEY_EXCHANGE_SOURCE = """\
# Telemetry Secure Channel Session Key Agreement
from cryptography.hazmat.primitives.asymmetric import ec


class GroundStationChannel:
    \"\"\"Negotiate symmetric AES session keys using ephemeral Diffie-Hellman.\"\"\"

    def __init__(self, private_key: ec.EllipticCurvePrivateKey):
        self.private_key = private_key

    def derive_shared_secret(self, peer_public_key: ec.EllipticCurvePublicKey) -> bytes:
        # Line 12: ECDH key exchange
        return self.private_key.exchange(ec.ECDH(), peer_public_key)
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


def _init_kex_repo(root: Path) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    _git(root, "init", "-q")
    _git(root, "config", "user.email", "comms@drone.internal")
    _git(root, "config", "user.name", "Comms Link Team")
    src = root / "src" / "telecom"
    src.mkdir(parents=True, exist_ok=True)
    (src / "channel.py").write_text(KEY_EXCHANGE_SOURCE, encoding="utf-8")
    _git(root, "add", ".")
    _git(root, "commit", "-q", "-m", "Implement ECDH telemetry channel key exchange")
    return root


def test_key_establishment_assessed_as_mlkem():
    """ContextAdvisorService evaluates ECDH key exchange as MIGRATE to ML-KEM-768."""
    advisor = ContextAdvisorService()
    domain = DomainProfile.autonomous_drone()

    assessment = advisor.assess_facts(
        algorithm="ECDH",
        api="EllipticCurvePrivateKey.exchange",
        primitive="asymmetric",
        library="cryptography",
        operation="exchange",
        file_path="src/telecom/channel.py",
        start_line=12,
        end_line=12,
        deterministic_role="key_establishment",
        deterministic_confidence="high",
        enclosing_function="derive_shared_secret",
        enclosing_class="GroundStationChannel",
        source_excerpt="return self.private_key.exchange(ec.ECDH(), peer_public_key)",
        domain_profile=domain,
    )

    # 1. Decision must be MIGRATE
    assert assessment.assessment == AssessmentDecision.MIGRATE
    assert assessment.pqc_migration_required is True

    # 2. Candidate must be ML-KEM (FIPS 203)
    assert assessment.migration_candidate is not None
    assert "ML-KEM" in assessment.migration_candidate

    # 3. Guardrail: Must NEVER recommend signature schemes (ML-DSA) for key agreement!
    assert "ML-DSA" not in assessment.migration_candidate
    assert "SLH-DSA" not in assessment.migration_candidate

    # 4. Authoritative citations must reference NIST FIPS 203
    citations = [src["document_id"] for src in assessment.knowledge_sources]
    assert any("FIPS-203" in c for c in citations)


def test_key_establishment_cli_scan_json_output(tmp_path: Path, capsys):
    """Running CLI scan on key exchange repo maps ECDH to ML-KEM candidate."""
    repo = _init_kex_repo(tmp_path / "kex-repo")

    _code, out, _err = _run(
        ["scan", str(repo), "--domain", "cloud-infrastructure", "--format", "json"],
        capsys,
    )

    data = json.loads(out)
    assert "findings" in data
    assert len(data["findings"]) >= 1

    ecdh_findings = [f for f in data["findings"] if f["observed"]["algorithm"] == "ECDH"]
    assert len(ecdh_findings) >= 1
    finding = ecdh_findings[0]

    assert "contextual_assessment" in finding
    ca = finding["contextual_assessment"]
    assert ca is not None
    assert ca["assessment"] == "MIGRATE"
    assert ca["pqc_migration_required"] is True
    assert "ML-KEM" in (ca["migration_candidate"] or "")
    assert "ML-DSA" not in (ca["migration_candidate"] or "")
