"""Unit tests for the common CLI result model (``app.cli.results``)."""

from __future__ import annotations

from app.cli.results import CliFinding

REMOTE_DTO = {
    "id": "finding-1",
    "scan_id": "scan-1",
    "fingerprint": "abc123",
    "observed": {
        "rule_id": "PY-CRYPTO-RSA",
        "algorithm": "RSA",
        "api": "RSAPrivateKey.sign",
        "primitive": "RSA",
        "library": "cryptography",
        "operation": "SIGN",
        "location": {"file_path": "src/s.py", "start_line": 42, "end_line": 44},
        "source_excerpt": "key.sign(...)",
        "parser_version": "python-ast-1",
        "ruleset_version": "0.3.0",
    },
    "inference": {
        "role": "DIGITAL_SIGNATURE",
        "rationale": ["sign op"],
        "confidence": "HIGH",
        "evidence_basis": None,
    },
    "migration": {
        "review_path": "ML-DSA / SLH-DSA",
        "rationale": "broken by Shor",
        "is_migration_candidate": True,
        "pqc_ruleset_version": "0.2.0",
        "current": "RSA",
    },
    "impact": {
        "scope": "STATICALLY_OBSERVED",
        "node_count": 2,
        "nodes": ["RSA", "RSAPrivateKey.sign"],
        "relationships": ["USES"],
    },
    "priority": {"level": "HIGH", "score": 110, "reasons": ["asymmetric"]},
    "review": {"status": "OPEN", "assigned_to": None, "note": None, "updated_at": None},
}


def test_from_finding_dto_maps_every_block() -> None:
    finding = CliFinding.from_finding_dto(REMOTE_DTO)
    assert finding.finding_id == "finding-1"
    assert finding.fingerprint == "abc123"
    assert finding.algorithm == "RSA"
    assert finding.role == "DIGITAL_SIGNATURE"
    assert finding.review_path == "ML-DSA / SLH-DSA"
    assert finding.is_migration_candidate is True
    assert finding.impact_nodes == ["RSA", "RSAPrivateKey.sign"]
    assert finding.priority_level == "HIGH"
    assert finding.review_status == "OPEN"


def test_to_dict_groups_and_keeps_null_not_fabricated() -> None:
    finding = CliFinding.from_finding_dto({**REMOTE_DTO, "review": None})
    payload = finding.to_dict()
    assert set(payload) >= {
        "observed",
        "inference",
        "migration_review",
        "impact",
        "priority",
        "review",
    }
    assert payload["review"]["status"] is None  # unavailable -> null, never invented
    assert payload["observed"]["evidence"] == "key.sign(...)"


def test_priority_rank_orders_bands() -> None:
    high = CliFinding.from_finding_dto(REMOTE_DTO)
    low = CliFinding.from_finding_dto({**REMOTE_DTO, "priority": {"level": "LOW", "score": 5}})
    assert high.priority_rank > low.priority_rank


def test_summary_dto_is_partial_but_safe() -> None:
    finding = CliFinding.from_summary_dto(
        {
            "id": "f1",
            "algorithm": "AES",
            "operation": "ENCRYPT",
            "priority": "MEDIUM",
            "file_path": "a.py",
            "start_line": 3,
        }
    )
    assert finding.algorithm == "AES"
    assert finding.source_excerpt is None
    assert finding.to_dict()["observed"]["evidence"] is None


def test_sort_key_is_stable_and_path_based() -> None:
    a = CliFinding.from_summary_dto({"file_path": "a.py", "start_line": 10, "fingerprint": "z"})
    b = CliFinding.from_summary_dto({"file_path": "a.py", "start_line": 2, "fingerprint": "y"})
    assert sorted([a, b], key=lambda f: f.sort_key) == [b, a]
