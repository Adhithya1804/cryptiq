"""Unit tests for the CLI SARIF 2.1.0 emitter (``app.cli.sarif``)."""

from __future__ import annotations

from app.cli.results import CliFinding
from app.cli.sarif import build_sarif


def _finding(**overrides) -> CliFinding:
    base = {
        "fingerprint": "fp-1",
        "finding_id": None,
        "rule_id": "PY-CRYPTO-RSA",
        "algorithm": "RSA",
        "api": "rsa.generate_private_key",
        "operation": "KEY_GENERATION",
        "file_path": "src/keys.py",
        "start_line": 10,
        "end_line": 12,
        "role": "DIGITAL_SIGNATURE",
        "confidence": "HIGH",
        "review_path": "ML-DSA / SLH-DSA",
        "is_migration_candidate": True,
        "priority_level": "HIGH",
        "priority_score": 110,
    }
    base.update(overrides)
    return CliFinding(**base)


def test_document_shape_is_sarif_211() -> None:
    doc = build_sarif([_finding()])
    assert doc["version"] == "2.1.0"
    assert doc["$schema"].endswith("sarif-2.1.0.json")
    run = doc["runs"][0]
    assert run["tool"]["driver"]["name"] == "Cryptiq"
    assert run["columnKind"] == "unicodeCodePoints"


def test_rule_id_and_level_mapping() -> None:
    doc = build_sarif(
        [
            _finding(),
            _finding(algorithm="SHA-256", operation="HASH", priority_level="MEDIUM"),
            _finding(algorithm="ML-KEM", operation="KEY_ESTABLISHMENT", priority_level="LOW"),
        ]
    )
    results = doc["runs"][0]["results"]
    assert results[0]["ruleId"] == "cryptiq/rsa-key_generation"
    assert results[0]["level"] == "error"
    assert results[1]["level"] == "warning"
    assert results[2]["level"] == "note"
    # rules are sorted and de-duplicated
    rule_ids = [r["id"] for r in doc["runs"][0]["tool"]["driver"]["rules"]]
    assert rule_ids == sorted(rule_ids)


def test_paths_are_repo_relative_never_absolute() -> None:
    doc = build_sarif([_finding(file_path="./src/keys.py"), _finding(file_path="/abs/keys.py")])
    uris = [
        r["locations"][0]["physicalLocation"]["artifactLocation"]["uri"]
        for r in doc["runs"][0]["results"]
    ]
    assert uris[0] == "src/keys.py"
    assert not uris[1].startswith("/")


def test_partial_fingerprints_are_stable() -> None:
    doc = build_sarif([_finding()])
    pf = doc["runs"][0]["results"][0]["partialFingerprints"]
    assert pf["cryptiqFingerprint/v1"] == "fp-1"
    assert pf["cryptiqFindingId/v1"] == "fp-1"  # falls back to fingerprint locally
    assert pf["cryptiqFindingKey/v1"] == "src/keys.py:10:cryptiq/rsa-key_generation"


def test_build_is_deterministic() -> None:
    findings = [_finding(), _finding(algorithm="AES", operation="ENCRYPT")]
    assert build_sarif(findings) == build_sarif(findings)


def test_remote_finding_id_used_when_present() -> None:
    doc = build_sarif([_finding(finding_id="uuid-9")])
    pf = doc["runs"][0]["results"][0]["partialFingerprints"]
    assert pf["cryptiqFindingId/v1"] == "uuid-9"
    assert pf["cryptiqFingerprint/v1"] == "fp-1"
