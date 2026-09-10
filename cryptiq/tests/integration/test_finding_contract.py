"""The canonical response shape: what a client actually receives.

These tests pin the field names and the nesting. The point is not that the
serialisation runs, but that observed facts stay separate from inferences and
that no fact appears twice under two names.
"""

from datetime import UTC, datetime
from pathlib import Path

import pytest

from app.db.models import ReviewItem
from app.db.models.enums import ReviewStatus
from app.engine.ingestion import IngestionLimits, RepositoryReference, SourceSnapshot
from app.engine.ingestion.service import build_result
from app.engine.pipeline import analyze_snapshot
from app.schemas.finding import FindingRead, FindingSummary
from app.services import to_finding, to_page, to_review_queue, to_summary
from tests.support import write_tree

LIMITS = IngestionLimits(
    max_archive_bytes=1024 * 1024,
    max_extracted_bytes=1024 * 1024,
    max_files=100,
    max_file_bytes=4096,
)

REFERENCE = RepositoryReference(
    provider="github",
    owner="pyca",
    name="cryptography",
    canonical_url="https://github.com/pyca/cryptography",
)

COMMIT = "1f903f5ed2e5e316f345a927555e48535829d8de"
SCAN_ID = "scan-1"

TREE = {
    "src/signing.py": (
        b"from cryptography.hazmat.primitives.asymmetric import rsa\n"
        b"\n"
        b"class Signer:\n"
        b"    def sign(self, key: rsa.RSAPrivateKey, payload):\n"
        b"        return key.sign(payload)\n"
    ),
    "src/hashing.py": (
        b"from cryptography.hazmat.primitives import hashes\n"
        b"digest = hashes.SHA1()\n"
    ),
}


@pytest.fixture
def analysis(tmp_path: Path):
    root = write_tree(tmp_path / "snapshot", TREE)
    snapshot = SourceSnapshot(
        root_path=root,
        repository=REFERENCE,
        commit_sha=COMMIT,
        content_hash="0" * 64,
        file_count=len(TREE),
    )
    return analyze_snapshot(build_result(snapshot, LIMITS), root)


def signature_finding(analysis):
    return next(f for f in analysis.findings if f.match.api == "RSAPrivateKey.sign")


def hash_finding(analysis):
    return next(f for f in analysis.findings if f.match.primitive == "HASH")


def serialise(finding, review: ReviewItem | None = None) -> FindingRead:
    return to_finding(
        finding,
        scan_id=SCAN_ID,
        repository=REFERENCE,
        commit_sha=COMMIT,
        review=review,
    )


def test_the_top_level_keys_are_exactly_the_canonical_ones(analysis) -> None:
    payload = serialise(signature_finding(analysis)).model_dump(mode="json")

    assert set(payload) == {
        "id",
        "scan_id",
        "repository",
        "commit_sha",
        "observed",
        "inference",
        "migration",
        "impact",
        "priority",
        "review",
    }


def test_observed_holds_only_checkable_facts(analysis) -> None:
    observed = serialise(signature_finding(analysis)).observed

    assert observed.algorithm == "RSA"
    assert observed.api == "RSAPrivateKey.sign"
    assert observed.operation.value == "SIGN"
    assert observed.rule_id == "PY-CRYPTO-RSA"
    assert observed.library == "cryptography"
    assert observed.location.file_path == "src/signing.py"
    assert observed.location.start_line == 5
    assert observed.location.end_line == 5
    assert observed.source_excerpt.strip() == "return key.sign(payload)"
    assert observed.enclosing_function == "Signer.sign"
    assert observed.enclosing_class == "Signer"
    assert observed.parser_version == "python-ast-1"
    assert observed.ruleset_version == "0.3.0"


def test_the_inference_is_separate_from_the_observation(analysis) -> None:
    payload = serialise(signature_finding(analysis)).model_dump(mode="json")

    assert payload["inference"]["role"] == "DIGITAL_SIGNATURE"
    assert payload["inference"]["confidence"] == "HIGH"
    assert payload["inference"]["evidence_basis"] == "CLASS_ANNOTATION"
    assert payload["inference"]["rationale"]
    # The role must not leak into the observed block, where it would read as
    # something a reviewer could check against the file.
    assert "role" not in payload["observed"]
    assert "confidence" not in payload["observed"]


def test_the_migration_block_is_a_review_path(analysis) -> None:
    migration = serialise(signature_finding(analysis)).migration

    assert migration.review_path.value == "ML-DSA / SLH-DSA"
    assert migration.is_migration_candidate is True
    assert migration.pqc_ruleset_version == "0.2.0"
    assert "Review against" in migration.rationale


def test_a_hash_finding_is_not_a_migration_candidate(analysis) -> None:
    payload = serialise(hash_finding(analysis)).model_dump(mode="json")

    assert payload["observed"]["algorithm"] == "SHA-1"
    assert payload["inference"]["role"] == "HASH"
    assert payload["migration"]["review_path"] == "HASH / POLICY REVIEW"
    assert payload["migration"]["is_migration_candidate"] is False


def test_the_impact_block_carries_the_graph(analysis) -> None:
    impact = serialise(signature_finding(analysis)).impact

    assert impact.scope.value == "STATICALLY_OBSERVED"
    assert impact.node_count == len(impact.nodes)
    assert {node.node_type for node in impact.nodes} >= {"ALGORITHM", "API", "FILE"}
    assert all(edge.relationship for edge in impact.relationships)


def test_the_priority_block_explains_itself(analysis) -> None:
    priority = serialise(signature_finding(analysis)).priority

    assert priority.level in {"CRITICAL", "HIGH", "MEDIUM", "LOW", "INFORMATIONAL"}
    assert priority.score > 0
    assert any("Shor" in reason for reason in priority.reasons)
    assert any("DIGITAL_SIGNATURE" in reason for reason in priority.reasons)


def test_review_is_absent_until_a_review_exists(analysis) -> None:
    assert serialise(signature_finding(analysis)).review is None


def test_review_is_serialised_when_present(session, finding, analysis) -> None:
    review = ReviewItem(finding_id=finding.id, assigned_to="a-reviewer", note="checking")
    session.add(review)
    session.commit()

    payload = serialise(signature_finding(analysis), review).model_dump(mode="json")

    assert payload["review"]["status"] == "OPEN"
    assert payload["review"]["assigned_to"] == "a-reviewer"
    assert payload["review"]["note"] == "checking"
    assert payload["review"]["id"] == review.id


def test_the_finding_id_is_the_fingerprint(analysis) -> None:
    finding = signature_finding(analysis)

    assert serialise(finding).id == finding.fingerprint
    assert len(finding.fingerprint) == 64


def test_no_fact_appears_under_two_names(analysis) -> None:
    """One canonical field per fact: no algorithm beside an observed_algorithm."""
    payload = serialise(signature_finding(analysis)).model_dump(mode="json")

    def leaf_keys(value, prefix=""):
        if isinstance(value, dict):
            for key, item in value.items():
                yield from leaf_keys(item, key)
        elif isinstance(value, list):
            for item in value:
                yield from leaf_keys(item, prefix)
        else:
            yield prefix

    keys = list(leaf_keys(payload))
    for banned in ("observed_algorithm", "crypto_algorithm", "detected_algorithm"):
        assert banned not in keys
    assert keys.count("algorithm") == 1
    assert keys.count("api") == 1
    assert keys.count("role") == 1


def test_a_summary_carries_the_columns_a_table_needs(analysis) -> None:
    summary = to_summary(signature_finding(analysis), scan_id=SCAN_ID)

    assert isinstance(summary, FindingSummary)
    assert set(summary.model_dump(mode="json")) == {
        "id",
        "scan_id",
        "algorithm",
        "api",
        "operation",
        "role",
        "confidence",
        "review_path",
        "is_migration_candidate",
        "priority",
        "priority_score",
        "file_path",
        "start_line",
        "end_line",
        "review_status",
    }


def test_a_page_preserves_the_engine_order(analysis) -> None:
    page = to_page(analysis, scan_id=SCAN_ID)

    assert page.total == len(analysis.findings)
    assert [item.id for item in page.findings] == [f.fingerprint for f in analysis.findings]


def test_the_review_queue_is_ordered_by_priority_then_position(analysis) -> None:
    reviews = [
        ReviewItem(
            id=f"review-{index}",
            finding_id=f"finding-{index}",
            status=ReviewStatus.OPEN,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        for index, _ in enumerate(analysis.findings)
    ]
    pairs = list(zip(analysis.findings, reviews, strict=True))

    queue = to_review_queue(pairs, scan_id=SCAN_ID)

    scores = [item.priority_score for item in queue.items]
    assert scores == sorted(scores, reverse=True)
    assert queue.total == len(pairs)
    assert set(queue.items[0].model_dump(mode="json")) == {
        "review_id",
        "finding_id",
        "scan_id",
        "algorithm",
        "api",
        "role",
        "review_path",
        "priority",
        "priority_score",
        "status",
        "assigned_to",
        "note",
        "file_path",
        "start_line",
        "updated_at",
    }


def test_the_review_queue_is_ordered_deterministically(analysis) -> None:
    reviews = [
        ReviewItem(
            id=f"review-{index}",
            finding_id=f"finding-{index}",
            status=ReviewStatus.OPEN,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        for index, _ in enumerate(analysis.findings)
    ]
    pairs = list(zip(analysis.findings, reviews, strict=True))

    first = to_review_queue(pairs, scan_id=SCAN_ID)
    second = to_review_queue(list(reversed(pairs)), scan_id=SCAN_ID)

    assert [item.finding_id for item in first.items] == [
        item.finding_id for item in second.items
    ]


def test_serialisation_is_deterministic(analysis) -> None:
    finding = signature_finding(analysis)

    assert serialise(finding).model_dump(mode="json") == serialise(finding).model_dump(
        mode="json"
    )
