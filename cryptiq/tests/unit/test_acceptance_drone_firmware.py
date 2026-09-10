"""Synthetic Acceptance Test: Autonomous Drone Firmware Signing & OTA Verification.

Product Thesis & Acceptance Criteria:
- Detect cryptography: ECDSA is detected deterministically from static analysis.
- Understand semantic role: Engine extracts that ECDSA signs/verifies firmware manifests and boot images.
- Understand domain context: Autonomous Drone profile with constrained telemetry bandwidth and storage.
- Authoritative knowledge: NIST FIPS 204 (ML-DSA) and avionics guidance.
- Migration assessment: Output is MIGRATE (or REVIEW with migration candidate ML-DSA-65).
- Guardrail invariant: NEVER map digital signatures to ML-KEM (KEM category error!).
- Engineering trade-offs: Must explicitly identify the signature size overhead (~3.3 KB vs 64B)
  and its impact on low-bandwidth telemetry links and firmware partition sizes.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from app.cli.main import main
from app.engine.context.models import AssessmentDecision, DomainProfile
from app.services.context_advisor import ContextAdvisorService

FIRMWARE_SIGNER_SOURCE = """\
# Drone Secure Boot & Firmware Update Verification Service
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives import hashes


class DroneFirmwareVerifier:
    \"\"\"Verify cryptographic signatures on incoming OTA firmware update packages.\"\"\"

    def __init__(self, public_key: ec.EllipticCurvePublicKey):
        self.public_key = public_key

    def verify_update_manifest(self, manifest_payload: bytes, signature: bytes) -> bool:
        # Line 13: ECDSA signature verification on firmware manifest
        try:
            self.public_key.verify(
                signature,
                manifest_payload,
                ec.ECDSA(hashes.SHA256()),
            )
            return True
        except Exception:
            return False
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


def _init_firmware_repo(root: Path) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    _git(root, "init", "-q")
    _git(root, "config", "user.email", "security@drone.internal")
    _git(root, "config", "user.name", "UAV Security Team")
    src = root / "src" / "bootloader"
    src.mkdir(parents=True, exist_ok=True)
    (src / "firmware_verifier.py").write_text(FIRMWARE_SIGNER_SOURCE, encoding="utf-8")
    _git(root, "add", ".")
    _git(root, "commit", "-q", "-m", "Implement drone OTA firmware signature verification")
    return root


def test_drone_firmware_ecdsa_assessed_as_migrate_with_tradeoffs():
    """ContextAdvisorService evaluates drone firmware signing with signature size trade-offs."""
    advisor = ContextAdvisorService()
    domain = DomainProfile.autonomous_drone()

    assessment = advisor.assess_facts(
        algorithm="ECDSA",
        api="EllipticCurvePublicKey.verify",
        primitive="asymmetric",
        library="cryptography",
        operation="verify",
        file_path="src/bootloader/firmware_verifier.py",
        start_line=13,
        end_line=18,
        deterministic_role="digital_signature",
        deterministic_confidence="high",
        enclosing_function="verify_update_manifest",
        enclosing_class="DroneFirmwareVerifier",
        source_excerpt="self.public_key.verify(signature, manifest_payload, ec.ECDSA(hashes.SHA256()))",
        domain_profile=domain,
    )

    # 1. Decision must indicate migration is needed
    assert assessment.assessment in (AssessmentDecision.MIGRATE, AssessmentDecision.REVIEW)
    assert assessment.pqc_migration_required is True

    # 2. Migration candidate must be ML-DSA (FIPS 204)
    assert assessment.migration_candidate is not None
    assert "ML-DSA" in assessment.migration_candidate

    # 3. Guardrail: Must NEVER recommend ML-KEM for digital signatures!
    assert "ML-KEM" not in assessment.migration_candidate

    # 4. Engineering trade-offs must address signature size and telemetry bandwidth
    tradeoffs_text = " ".join(assessment.engineering_tradeoffs).lower()
    assert (
        "signature size" in tradeoffs_text
        or "bandwidth" in tradeoffs_text
        or "bytes" in tradeoffs_text
        or "overhead" in tradeoffs_text
    )

    # 5. Authoritative citations must reference NIST FIPS 204 or avionics guidance
    citations = [src["document_id"] for src in assessment.knowledge_sources]
    assert any("FIPS-204" in c or "AVIONICS" in c for c in citations)


def test_drone_firmware_cli_scan_json_output(tmp_path: Path, capsys):
    """Running CLI scan on firmware repo with --domain autonomous-drone flags ECDSA for migration."""
    repo = _init_firmware_repo(tmp_path / "firmware-repo")

    _code, out, _err = _run(
        ["scan", str(repo), "--domain", "autonomous-drone", "--format", "json"],
        capsys,
    )

    data = json.loads(out)
    assert "findings" in data
    assert len(data["findings"]) >= 1

    ecdsa_findings = [f for f in data["findings"] if f["observed"]["algorithm"] == "ECDSA"]
    assert len(ecdsa_findings) >= 1
    finding = ecdsa_findings[0]

    assert "contextual_assessment" in finding
    ca = finding["contextual_assessment"]
    assert ca is not None
    assert ca["assessment"] in ("MIGRATE", "REVIEW")
    assert ca["pqc_migration_required"] is True
    assert "ML-DSA" in (ca["migration_candidate"] or "")
    assert ca["domain_profile"]["domain"] == "AUTONOMOUS_DRONE"
