"""CLI tests.

The CLI is a client of the ``/api/v1`` HTTP contract, so these tests stand a
fake API up with :class:`httpx.MockTransport` and assert on what the commands
print and which exit code they return. No backend, no database, no GitHub.
"""

from __future__ import annotations

import json
from collections.abc import Callable

import httpx
import pytest

from app.cli.client import CryptiqClient
from app.cli.main import main

# --------------------------------------------------------------------------- #
# fake API
# --------------------------------------------------------------------------- #

Handler = Callable[[httpx.Request], httpx.Response]


def _json(payload: dict, status_code: int = 200) -> httpx.Response:
    return httpx.Response(status_code, json=payload)


def _error(code: str, message: str, status_code: int) -> httpx.Response:
    return httpx.Response(status_code, json={"error": {"code": code, "message": message}})


INSPECTION = {
    "id": "scan-1",
    "repository_id": "repo-1",
    "repository": {
        "provider": "github",
        "owner": "pyca",
        "name": "cryptography",
        "url": "https://github.com/pyca/cryptography",
    },
    "language": "Python",
    "commit_sha": "1f903f5ed2e5e316f345a927555e48535829d8de",
    "status": "QUEUED",
    "started_at": None,
    "completed_at": None,
    "duration_ms": None,
    "files_analyzed": None,
    "findings_count": 0,
    "severity": {"critical": 0, "high": 0, "medium": 0, "low": 0},
    "error_code": None,
    "error_message": None,
    "cached": False,
}

COMPLETED = {
    **INSPECTION,
    "status": "COMPLETED",
    "started_at": "2026-09-09T17:42:40",
    "completed_at": "2026-09-09T17:47:19",
    "duration_ms": 278655,
    "files_analyzed": 241,
    "findings_count": 1042,
    "severity": {"critical": 0, "high": 136, "medium": 906, "low": 0},
}

SUMMARY_ROW = {
    "id": "finding-1",
    "scan_id": "scan-1",
    "algorithm": "RSA",
    "api": "RSAPrivateKey.sign",
    "operation": "SIGN",
    "role": "DIGITAL_SIGNATURE",
    "confidence": "HIGH",
    "review_path": "ML-DSA / SLH-DSA",
    "is_migration_candidate": True,
    "priority": "HIGH",
    "priority_score": 110,
    "file_path": "src/cryptography/very/deep/module/signing.py",
    "start_line": 42,
    "end_line": 44,
    "review_status": "OPEN",
}

FINDING_DETAIL = {
    "id": "finding-1",
    "scan_id": "scan-1",
    "repository": INSPECTION["repository"],
    "commit_sha": INSPECTION["commit_sha"],
    "language": "Python",
    "observed": {
        "rule_id": "PY-CRYPTO-RSA",
        "algorithm": "RSA",
        "api": "RSAPrivateKey.sign",
        "primitive": "PUBLIC_KEY",
        "library": "cryptography",
        "operation": "SIGN",
        "location": {
            "file_path": "src/signing.py",
            "start_line": 42,
            "end_line": 44,
            "start_column": 4,
            "end_column": 20,
        },
        "source_excerpt": "key.sign(payload, padding.PKCS1v15(), hashes.SHA256())",
        "parser_version": "python-ast-1",
        "ruleset_version": "0.3.0",
    },
    "inference": {
        "role": "DIGITAL_SIGNATURE",
        "rationale": ["RSAPrivateKey.sign performs a sign operation."],
        "confidence": "HIGH",
        "evidence_basis": None,
    },
    "migration": {
        "review_path": "ML-DSA / SLH-DSA",
        "rationale": "RSA signatures are broken by Shor's algorithm.",
        "is_migration_candidate": True,
        "pqc_ruleset_version": "0.2.0",
        "current": "RSA",
    },
    "impact": {
        "scope": "STATICALLY_OBSERVED",
        "node_count": 4,
        "nodes": ["RSA", "RSAPrivateKey.sign", "Signer.sign", "src/signing.py"],
        "relationships": ["USES", "CALLS", "DEFINED_IN"],
    },
    "priority": {
        "level": "HIGH",
        "score": 110,
        "reasons": ["RSA is public-key cryptography broken by Shor's algorithm."],
    },
    "review": None,
    "ai_explanation_available": False,
}

QUEUE_ITEM = {
    "review_id": "review-1",
    "finding_id": "finding-1",
    "scan_id": "scan-1",
    "algorithm": "RSA",
    "api": "RSAPrivateKey.sign",
    "role": "DIGITAL_SIGNATURE",
    "review_path": "ML-DSA / SLH-DSA",
    "priority": "HIGH",
    "priority_score": 110,
    "status": "OPEN",
    "assigned_to": None,
    "note": None,
    "reasons": [],
    "file_path": "src/signing.py",
    "start_line": 42,
    "updated_at": None,
}


@pytest.fixture
def invoke(capsys: pytest.CaptureFixture[str]):
    """Return ``invoke(argv, handler) -> (exit_code, stdout, stderr)``."""

    def _invoke(argv: list[str], handler: Handler) -> tuple[int, str, str]:
        def factory(_url: str | None) -> CryptiqClient:
            return CryptiqClient("http://testserver/api/v1", transport=httpx.MockTransport(handler))

        code = main(argv, client_factory=factory)
        captured = capsys.readouterr()
        return code, captured.out, captured.err

    return _invoke


# --------------------------------------------------------------------------- #
# scan
# --------------------------------------------------------------------------- #


def test_scan_queued(invoke) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.url.path == "/api/v1/scans"
        assert json.loads(request.content) == {
            "repository_url": "https://github.com/pyca/cryptography",
            "commit_sha": "1f903f5",
        }
        return _json(INSPECTION, status_code=202)

    code, out, _ = invoke(
        ["scan", "https://github.com/pyca/cryptography", "1f903f5"], handler
    )
    assert code == 0
    assert "Status: QUEUED" in out
    assert "Scan ID: scan-1" in out
    assert "CACHED" not in out


def test_scan_cached(invoke) -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return _json({**COMPLETED, "cached": True}, status_code=200)

    code, out, _ = invoke(
        ["scan", "https://github.com/pyca/cryptography", "1f903f5"], handler
    )
    assert code == 0
    assert "Status: CACHED" in out
    assert "Existing result reused." in out


def test_scan_json_mode_is_the_raw_dto(invoke) -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return _json(INSPECTION, status_code=202)

    code, out, _ = invoke(
        ["scan", "https://github.com/pyca/cryptography", "1f903f5", "--json"], handler
    )
    assert code == 0
    assert json.loads(out) == INSPECTION


def test_scan_invalid_repository_url_is_reported_not_raised(invoke) -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return _error("INVALID_REPOSITORY_URL", "Only github.com repositories are supported.", 422)

    code, _out, err = invoke(["scan", "https://example.com/x/y", "1f903f5"], handler)
    assert code == 1
    assert "github.com" in err
    assert "Traceback" not in err


# --------------------------------------------------------------------------- #
# scan-status
# --------------------------------------------------------------------------- #


def test_scan_status_completed(invoke) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v1/scans/scan-1"
        return _json(COMPLETED)

    code, out, _ = invoke(["scan-status", "scan-1"], handler)
    assert code == 0
    assert "Status:           COMPLETED" in out
    assert "Findings:         1042" in out
    assert "Resolved commit:  1f903f5ed2e5e316f345a927555e48535829d8de" in out


def test_scan_status_failed_exits_3(invoke) -> None:
    payload = {
        **INSPECTION,
        "status": "FAILED",
        "error_code": "COMMIT_NOT_FOUND",
        "error_message": "The requested commit does not exist.",
    }

    def handler(_request: httpx.Request) -> httpx.Response:
        return _json(payload)

    code, out, _ = invoke(["scan-status", "scan-1"], handler)
    assert code == 3
    assert "Error code:       COMMIT_NOT_FOUND" in out


def test_scan_status_unknown_id_exits_4(invoke) -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return _error("not_found", "No inspection with id 'nope'.", 404)

    code, _out, err = invoke(["scan-status", "nope"], handler)
    assert code == 4
    assert "No inspection with id" in err


# --------------------------------------------------------------------------- #
# findings
# --------------------------------------------------------------------------- #


def _page(items: list[dict], *, total: int, page: int = 1, page_size: int = 50) -> dict:
    pages = max((total + page_size - 1) // page_size, 1)
    return {"items": items, "total": total, "page": page, "page_size": page_size, "pages": pages}


def test_findings_table_and_pagination_footer(invoke) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v1/scans/scan-1/findings"
        assert request.url.params["page"] == "1"
        assert request.url.params["page_size"] == "50"
        return _json(_page([SUMMARY_ROW], total=1042))

    code, out, _ = invoke(["findings", "scan-1"], handler)
    assert code == 0
    assert "finding-1" in out
    assert "RSA" in out
    assert "Page 1 / 21" in out
    assert "Total findings: 1042" in out
    # a long path is truncated for the terminal
    assert "src/cryptography/very/deep/module/signing.py" not in out


def test_findings_filters_are_sent_to_the_server(invoke) -> None:
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(dict(request.url.params))
        return _json(_page([], total=0))

    code, _out, _ = invoke(
        [
            "findings",
            "scan-1",
            "--priority",
            "high",
            "--algorithm",
            "rsa",
            "--role",
            "digital_signature",
            "--status",
            "open",
            "--confidence",
            "high",
            "--page",
            "2",
            "--page-size",
            "10",
        ],
        handler,
    )
    assert code == 0
    assert seen["priority"] == "high"
    assert seen["algorithm"] == "rsa"
    assert seen["role"] == "digital_signature"
    assert seen["status"] == "open"
    assert seen["confidence"] == "high"
    assert seen["page"] == "2"
    assert seen["page_size"] == "10"


def test_findings_rejects_unknown_priority_with_usage_exit(invoke) -> None:
    def handler(_request: httpx.Request) -> httpx.Response:  # pragma: no cover
        raise AssertionError("the request should never be sent")

    with pytest.raises(SystemExit) as exc:
        invoke(["findings", "scan-1", "--priority", "bogus"], handler)
    assert exc.value.code == 2


def test_findings_json_mode_passes_the_envelope_through(invoke) -> None:
    envelope = _page([SUMMARY_ROW], total=1)

    def handler(_request: httpx.Request) -> httpx.Response:
        return _json(envelope)

    code, out, _ = invoke(["findings", "scan-1", "--json"], handler)
    assert code == 0
    assert json.loads(out) == envelope


# --------------------------------------------------------------------------- #
# finding detail
# --------------------------------------------------------------------------- #


def test_finding_detail_renders_every_block(invoke) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v1/findings/finding-1"
        return _json(FINDING_DETAIL)

    code, out, _ = invoke(["finding", "finding-1"], handler)
    assert code == 0
    for heading in ("Observed", "Inference", "Migration", "Impact", "Priority", "Review"):
        assert heading in out
    assert "PY-CRYPTO-RSA" in out
    assert "ML-DSA / SLH-DSA" in out
    # review is null -> explicit unavailable state, no fabricated fields
    assert "N/A (no review opened)" in out


def test_finding_detail_marks_missing_scalars_as_na(invoke) -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return _json(FINDING_DETAIL)

    _code, out, _ = invoke(["finding", "finding-1"], handler)
    assert "evidence basis  N/A" in out


def test_finding_detail_unknown_id_exits_4(invoke) -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return _error("not_found", "No finding with id 'nope'.", 404)

    code, _out, err = invoke(["finding", "nope"], handler)
    assert code == 4
    assert "No finding with id" in err


# --------------------------------------------------------------------------- #
# review queue
# --------------------------------------------------------------------------- #


def test_review_queue_lists_and_counts(invoke) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v1/review-queue"
        return _json({"items": [QUEUE_ITEM], "total": 132})

    code, out, _ = invoke(["review-queue"], handler)
    assert code == 0
    assert "review-1" in out
    assert "Review items: 132" in out


def test_review_queue_forwards_filters(invoke) -> None:
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(dict(request.url.params))
        return _json({"items": [], "total": 0})

    code, _out, _ = invoke(
        ["review-queue", "--algorithm", "rsa", "--priority", "high", "--status", "open"],
        handler,
    )
    assert code == 0
    assert seen == {"algorithm": "rsa", "priority": "high", "status": "open", "page_size": "50"}


def test_review_queue_json_mode(invoke) -> None:
    envelope = {"items": [QUEUE_ITEM], "total": 1}

    def handler(_request: httpx.Request) -> httpx.Response:
        return _json(envelope)

    _code, out, _ = invoke(["review-queue", "--json"], handler)
    assert json.loads(out) == envelope


# --------------------------------------------------------------------------- #
# review update
# --------------------------------------------------------------------------- #


def test_review_update_sends_only_the_fields_given(invoke) -> None:
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "PATCH"
        assert request.url.path == "/api/v1/review-items/review-1"
        seen.update(json.loads(request.content))
        return _json(
            {
                "id": "review-1",
                "status": "IN_REVIEW",
                "assigned_to": "alice",
                "note": None,
                "created_at": None,
                "updated_at": "2026-09-09T19:00:00",
            }
        )

    code, out, _ = invoke(
        ["review-update", "review-1", "--status", "in_review", "--assignee", "alice"],
        handler,
    )
    assert code == 0
    assert seen == {"status": "IN_REVIEW", "assigned_to": "alice"}
    assert "Status:      IN_REVIEW" in out


def test_review_update_without_fields_is_a_usage_error(invoke) -> None:
    def handler(_request: httpx.Request) -> httpx.Response:  # pragma: no cover
        raise AssertionError("no request expected")

    code, _out, err = invoke(["review-update", "review-1"], handler)
    assert code == 2
    assert "Nothing to update" in err


def test_review_update_invalid_transition_is_reported(invoke) -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return _error(
            "INVALID_REVIEW_TRANSITION",
            "A review cannot move from RESOLVED to OPEN.",
            409,
        )

    code, _out, err = invoke(
        ["review-update", "review-1", "--status", "open"], handler
    )
    assert code == 1
    assert "cannot move from" in err


# --------------------------------------------------------------------------- #
# demo
# --------------------------------------------------------------------------- #


def test_demo_polls_to_completion_then_summarises(invoke) -> None:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if request.method == "POST" and path == "/api/v1/scans":
            return _json(INSPECTION, status_code=202)
        if path == "/api/v1/scans/scan-1":
            calls["n"] += 1
            if calls["n"] == 1:
                return _json({**INSPECTION, "status": "RUNNING"})
            return _json(COMPLETED)
        if path == "/api/v1/scans/scan-1/findings":
            return _json(_page([SUMMARY_ROW], total=1042, page_size=5))
        if path == "/api/v1/review-queue":
            return _json({"items": [QUEUE_ITEM], "total": 132})
        raise AssertionError(f"unexpected {request.method} {path}")

    code, out, _ = invoke(["demo", "--poll-interval", "0", "--timeout", "5"], handler)
    assert code == 0
    assert "Findings: 1042" in out
    assert "Migration candidates" in out
    assert "Review queue items: 132" in out


def test_demo_reports_cache_reuse(invoke) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if request.method == "POST":
            return _json({**COMPLETED, "cached": True}, status_code=200)
        if path == "/api/v1/scans/scan-1/findings":
            return _json(_page([SUMMARY_ROW], total=1042, page_size=5))
        if path == "/api/v1/review-queue":
            return _json({"items": [], "total": 132})
        raise AssertionError(f"unexpected {path}")

    code, out, _ = invoke(["demo", "--poll-interval", "0"], handler)
    assert code == 0
    assert "Cached result reused." in out


def test_demo_scan_failure_exits_3(invoke) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            return _json(INSPECTION, status_code=202)
        return _json(
            {
                **INSPECTION,
                "status": "FAILED",
                "error_code": "ANALYSIS_FAILED",
                "error_message": "The analysis did not complete.",
            }
        )

    code, out, _ = invoke(["demo", "--poll-interval", "0", "--timeout", "5"], handler)
    assert code == 3
    assert "Scan failed: ANALYSIS_FAILED" in out


# --------------------------------------------------------------------------- #
# transport-level failures
# --------------------------------------------------------------------------- #


def test_backend_unreachable_is_a_friendly_error(invoke) -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    code, _out, err = invoke(["scan-status", "scan-1"], handler)
    assert code == 1
    assert "Could not reach the Cryptiq API" in err
    assert "Traceback" not in err


def test_no_subcommand_prints_help(invoke) -> None:
    """Bare ``cryptiq`` is a landing screen, not a usage error."""
    code, out, _err = invoke([], lambda _r: _json({}))
    assert code == 0
    assert "usage: cryptiq" in out
    assert "scan" in out and "diff" in out


def test_version_flag_prints_version(invoke) -> None:
    with pytest.raises(SystemExit) as exc:
        invoke(["--version"], lambda _r: _json({}))
    assert exc.value.code == 0
