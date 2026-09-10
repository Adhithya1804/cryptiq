"""Remote-mode tests for the merged ``scan`` command.

The pre-existing ``test_cli.py`` covers submit-only ``scan`` plus every other
remote command. This module covers the additions: URL auto-detection, the
``--wait`` poll-and-fetch path, and ``--format json`` / ``--format sarif`` over
the API. A fake ``/api/v1`` is stood up with ``httpx.MockTransport``.
"""

from __future__ import annotations

import json
from collections.abc import Callable

import httpx
import pytest

from app.cli.client import CryptiqClient
from app.cli.main import main

Handler = Callable[[httpx.Request], httpx.Response]

INSPECTION = {
    "id": "scan-1",
    "repository": {"provider": "github", "owner": "o", "name": "r",
                   "url": "https://github.com/o/r"},
    "commit_sha": "1f903f5ed2e5e316f345a927555e48535829d8de",
    "status": "QUEUED",
    "findings_count": 0,
    "severity": {"critical": 0, "high": 0, "medium": 0, "low": 0},
}
COMPLETED = {**INSPECTION, "status": "COMPLETED", "findings_count": 1}

FINDING_DETAIL = {
    "id": "finding-1",
    "scan_id": "scan-1",
    "fingerprint": "fp-remote-1",
    "observed": {
        "rule_id": "PY-CRYPTO-RSA",
        "algorithm": "RSA",
        "api": "rsa.generate_private_key",
        "primitive": "RSA",
        "library": "cryptography",
        "operation": "KEY_GENERATION",
        "location": {"file_path": "src/keys.py", "start_line": 10, "end_line": 12},
        "source_excerpt": "rsa.generate_private_key(...)",
        "parser_version": "python-ast-1",
        "ruleset_version": "0.3.0",
    },
    "inference": {"role": "DIGITAL_SIGNATURE", "rationale": ["x"], "confidence": "HIGH"},
    "migration": {
        "review_path": "ML-DSA / SLH-DSA", "rationale": "shor",
        "is_migration_candidate": True, "pqc_ruleset_version": "0.2.0", "current": "RSA",
    },
    "impact": {"scope": "STATICALLY_OBSERVED", "node_count": 1, "nodes": ["RSA"], "relationships": []},
    "priority": {"level": "HIGH", "score": 110, "reasons": ["asymmetric"]},
    "review": None,
}


@pytest.fixture
def invoke(capsys: pytest.CaptureFixture[str]):
    def _invoke(argv: list[str], handler: Handler) -> tuple[int, str, str]:
        def factory(_url: str | None) -> CryptiqClient:
            return CryptiqClient(
                "http://testserver/api/v1", transport=httpx.MockTransport(handler)
            )

        code = main(argv, client_factory=factory)
        cap = capsys.readouterr()
        return code, cap.out, cap.err

    return _invoke


def _full_handler(request: httpx.Request) -> httpx.Response:
    path = request.url.path
    if request.method == "POST" and path == "/api/v1/scans":
        return httpx.Response(202, json=INSPECTION)
    if path == "/api/v1/scans/scan-1":
        return httpx.Response(200, json=COMPLETED)
    if path == "/api/v1/scans/scan-1/findings":
        return httpx.Response(
            200,
            json={"items": [{"id": "finding-1"}], "total": 1, "page": 1,
                  "page_size": 200, "pages": 1},
        )
    if path == "/api/v1/findings/finding-1":
        return httpx.Response(200, json=FINDING_DETAIL)
    raise AssertionError(f"unexpected {request.method} {path}")


def test_url_target_auto_selects_remote(invoke) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        return httpx.Response(202, json=INSPECTION)

    code, out, _ = invoke(
        ["scan", "https://github.com/o/r", "1f903f5ed2e5e316f345a927555e48535829d8de"],
        handler,
    )
    assert code == 0
    assert "Status: QUEUED" in out


def test_remote_scan_requires_commit(invoke) -> None:
    code, _out, err = invoke(["scan", "https://github.com/o/r", "--remote"], _full_handler)
    assert code == 2
    assert "commit" in err.lower()


def test_remote_wait_fetches_and_renders_findings(invoke) -> None:
    code, out, _ = invoke(
        [
            "scan", "https://github.com/o/r", "--remote",
            "--commit", "1f903f5ed2e5e316f345a927555e48535829d8de",
            "--wait", "--poll-interval", "0",
        ],
        _full_handler,
    )
    assert code == 1  # a HIGH finding -> exit 1 under default --fail-on high
    assert "RSA" in out
    assert "Findings: 1" in out


def test_remote_wait_json(invoke) -> None:
    code, out, _ = invoke(
        [
            "scan", "https://github.com/o/r", "--remote",
            "--commit", "1f903f5ed2e5e316f345a927555e48535829d8de",
            "--wait", "--json", "--poll-interval", "0", "--fail-on", "never",
        ],
        _full_handler,
    )
    assert code == 0
    payload = json.loads(out)
    assert payload["scan_id"] == "scan-1"
    assert payload["findings"][0]["observed"]["algorithm"] == "RSA"
    assert payload["findings"][0]["fingerprint"] == "fp-remote-1"


def test_remote_sarif_over_api(invoke) -> None:
    code, out, _ = invoke(
        [
            "scan", "https://github.com/o/r", "--remote",
            "--commit", "1f903f5ed2e5e316f345a927555e48535829d8de",
            "--format", "sarif", "--poll-interval", "0", "--fail-on", "never",
        ],
        _full_handler,
    )
    assert code == 0
    doc = json.loads(out)
    assert doc["version"] == "2.1.0"
    assert doc["runs"][0]["results"][0]["ruleId"] == "cryptiq/rsa-key_generation"
    pf = doc["runs"][0]["results"][0]["partialFingerprints"]
    assert pf["cryptiqFingerprint/v1"] == "fp-remote-1"


def test_remote_failed_scan_exits_3(invoke) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            return httpx.Response(202, json=INSPECTION)
        return httpx.Response(200, json={**INSPECTION, "status": "FAILED",
                                         "error_code": "ANALYSIS_FAILED"})

    code, _out, err = invoke(
        [
            "scan", "https://github.com/o/r", "--remote",
            "--commit", "1f903f5ed2e5e316f345a927555e48535829d8de",
            "--wait", "--poll-interval", "0",
        ],
        handler,
    )
    assert code == 3
    assert "FAILED" in err


def test_remote_unreachable_is_friendly(invoke) -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused")

    code, _out, err = invoke(
        ["scan", "https://github.com/o/r", "--remote", "--commit",
         "1f903f5ed2e5e316f345a927555e48535829d8de"],
        handler,
    )
    assert code == 1
    assert "Could not reach" in err
    assert "Traceback" not in err
