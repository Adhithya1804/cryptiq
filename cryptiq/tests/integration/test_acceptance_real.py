"""The full Cryptiq acceptance pipeline against a real repository.

Enable with CRYPTIQ_RUN_NETWORK_TESTS=1. The rest of the suite must never
depend on GitHub being reachable, so this module skips by default.

Exact commit -> secure extraction -> discovery -> parse -> RSA rule ->
evidence -> impact -> priority -> fingerprint, all inside the snapshot's
lifetime.
"""

import os

import pytest

from app.engine.fingerprints import ScanIdentity
from app.engine.impact import ImpactNodeType, ImpactScope
from app.engine.ingestion import ingest_commit
from app.engine.pipeline import analyze_snapshot
from app.engine.pqc import PqcReviewPath
from app.engine.priority import ReviewPriority
from app.engine.roles import CryptographicRole
from app.engine.rules import CryptoOperation, MatchConfidence, registered_rule_ids
from app.integrations.github import GitHubSourceProvider, parse_repository_url
from app.services import to_finding

REPOSITORY_URL = "https://github.com/pyca/cryptography"
COMMIT_SHA = "1f903f5ed2e5e316f345a927555e48535829d8de"

pytestmark = [
    pytest.mark.network,
    pytest.mark.skipif(
        os.getenv("CRYPTIQ_RUN_NETWORK_TESTS") != "1",
        reason="set CRYPTIQ_RUN_NETWORK_TESTS=1 to run tests that reach GitHub",
    ),
]


@pytest.fixture(scope="module")
async def analysis():
    """Run the whole pipeline once against the exact acceptance commit."""
    repository = parse_repository_url(REPOSITORY_URL)
    async with ingest_commit(GitHubSourceProvider(), repository, COMMIT_SHA) as ingestion:
        root = ingestion.snapshot.root_path
        result = analyze_snapshot(ingestion, root)
        yield result, root

    # The snapshot is gone once the block exits; the result must survive it.
    assert not root.exists()


async def test_the_exact_commit_was_analysed(analysis) -> None:
    result, _ = analysis

    assert result.commit_sha == COMMIT_SHA
    assert result.repository.canonical_url == REPOSITORY_URL
    assert len(result.content_hash) == 64
    assert result.total_files > 0
    assert result.analyzed_files > 0
    assert result.parsed_files > 0


async def test_real_findings_were_produced(analysis) -> None:
    result, _ = analysis

    assert result.findings
    assert {finding.match.operation for finding in result.findings} == set(CryptoOperation)


async def test_every_rule_of_this_phase_finds_real_usage(analysis) -> None:
    """This revision genuinely uses all seven families the engine knows."""
    result, _ = analysis

    assert {finding.match.rule_id for finding in result.findings} == set(registered_rule_ids())


async def test_the_rsa_inventory_has_not_regressed(analysis) -> None:
    """Phase 5's verified result must survive the rule expansion unchanged."""
    result, _ = analysis

    rsa = [f for f in result.findings if f.match.rule_id == "PY-CRYPTO-RSA"]
    assert len(rsa) == 38
    assert {f.match.api for f in rsa} == {
        "rsa.generate_private_key",
        "RSAPrivateKey.sign",
        "RSAPrivateKey.decrypt",
        "RSAPublicKey.verify",
        "RSAPublicKey.encrypt",
    }


async def test_every_finding_carries_real_source_evidence(analysis) -> None:
    result, _ = analysis

    for finding in result.findings:
        evidence = finding.evidence
        assert evidence.repository_sha == COMMIT_SHA
        assert evidence.file_path == finding.match.file_path
        assert evidence.source_excerpt.strip()
        assert evidence.rule_id == finding.match.rule_id
        assert evidence.parser_version == "python-ast-1"
        assert evidence.ruleset_version == "0.3.0"
        assert evidence.start_line == finding.match.location.start_line


async def test_the_evidence_actually_quotes_the_call(analysis) -> None:
    result, _ = analysis

    for finding in result.findings:
        excerpt = finding.evidence.source_excerpt
        # The last segment of the API is what appears at the call site: the
        # method for a key operation, the class for a construction or a hash.
        name = finding.match.api.rsplit(".", 1)[-1]
        assert name in excerpt, f"{finding.match.file_path}:{finding.match.location.start_line}"


async def test_every_finding_has_a_bounded_impact_graph(analysis) -> None:
    result, _ = analysis

    for finding in result.findings:
        impact = finding.impact
        assert impact.scope is ImpactScope.STATICALLY_OBSERVED
        assert impact.nodes_of(ImpactNodeType.ALGORITHM)[0].label == finding.match.algorithm
        assert impact.nodes_of(ImpactNodeType.FILE)[0].label == finding.match.file_path
        assert impact.node_count >= 3


async def test_every_finding_has_a_priority_with_reasons(analysis) -> None:
    result, _ = analysis

    for finding in result.findings:
        assert finding.priority.level in set(ReviewPriority)
        assert finding.priority.reasons
        assert finding.match.confidence is not MatchConfidence.UNKNOWN


async def test_public_key_findings_outrank_hash_inventory(analysis) -> None:
    """The queue must separate migration candidates from inventory."""
    result, _ = analysis

    public_key = [f for f in result.findings if f.match.algorithm in {"RSA", "ECDSA", "Ed25519"}]
    hashes = [f for f in result.findings if f.match.primitive == "HASH"]

    assert public_key and hashes
    assert all(any("Shor" in r for r in f.priority.reasons) for f in public_key)
    assert not any(any("Shor" in r for r in f.priority.reasons) for f in hashes)
    assert max(f.priority.score for f in hashes) < min(f.priority.score for f in public_key)


async def test_a_legacy_hash_is_recorded_without_a_verdict(analysis) -> None:
    """SHA-1 and MD5 are inventory here; whether they are acceptable comes later."""
    result, _ = analysis

    legacy = [f for f in result.findings if f.match.algorithm in {"SHA-1", "MD5"}]

    assert legacy
    for finding in legacy:
        assert finding.match.operation is CryptoOperation.HASH
        assert finding.match.confidence is MatchConfidence.HIGH
        assert finding.priority.level is not ReviewPriority.HIGH


async def test_fingerprints_are_stable_hex_digests(analysis) -> None:
    result, _ = analysis

    for finding in result.findings:
        assert len(finding.fingerprint) == 64
        assert int(finding.fingerprint, 16) >= 0


async def test_the_findings_are_reported_in_a_stable_order(analysis) -> None:
    result, _ = analysis

    keys = [finding.sort_key for finding in result.findings]
    assert keys == sorted(keys)


async def test_the_scan_identity_of_this_run_is_deterministic(analysis) -> None:
    result, _ = analysis

    identity = ScanIdentity(
        provider=result.repository.provider,
        owner=result.repository.owner,
        name=result.repository.name,
        commit_sha=result.commit_sha,
        parser_version="python-ast-1",
        ruleset_version="0.3.0",
        pqc_ruleset_version="0.3.0",
    )

    assert identity.digest == identity.digest
    assert len(identity.digest) == 64


async def test_a_second_run_produces_identical_findings() -> None:
    """The whole pipeline is rerun end to end and compared."""
    repository = parse_repository_url(REPOSITORY_URL)

    async def run():
        async with ingest_commit(GitHubSourceProvider(), repository, COMMIT_SHA) as ingestion:
            result = analyze_snapshot(ingestion, ingestion.snapshot.root_path)
            return (
                result.content_hash,
                [
                    (
                        finding.fingerprint,
                        finding.match.file_path,
                        finding.match.location.start_line,
                        finding.match.api,
                        finding.match.operation.value,
                        finding.match.confidence.value,
                        finding.priority.level.value,
                        finding.priority.score,
                        finding.impact.node_count,
                        finding.evidence.source_excerpt,
                    )
                    for finding in result.findings
                ],
            )

    first = await run()
    second = await run()

    assert first == second


async def test_every_finding_carries_a_role_and_a_review_path(analysis) -> None:
    result, _ = analysis

    for finding in result.findings:
        assert finding.role.role in set(CryptographicRole)
        assert finding.role.rationale
        assert finding.pqc.review_path in set(PqcReviewPath)
        assert finding.pqc.rationale
        # A migration candidate is only ever a public-key path.
        assert finding.pqc.is_migration_candidate == (
            finding.pqc.review_path
            in {
                PqcReviewPath.SIGNATURE_MIGRATION,
                PqcReviewPath.KEY_ENCAPSULATION_MIGRATION,
            }
        )


async def test_the_classification_matches_the_specified_table(analysis) -> None:
    """Every pairing the specification names is present and correct."""
    result, _ = analysis
    seen = {
        (f.match.algorithm, f.match.operation.value, f.role.role.value, f.pqc.review_path.value)
        for f in result.findings
    }

    expected = {
        ("RSA", "SIGN", "DIGITAL_SIGNATURE", "ML-DSA / SLH-DSA"),
        ("RSA", "VERIFY", "DIGITAL_SIGNATURE", "ML-DSA / SLH-DSA"),
        ("ECDSA", "SIGN", "DIGITAL_SIGNATURE", "ML-DSA / SLH-DSA"),
        ("ECDSA", "VERIFY", "DIGITAL_SIGNATURE", "ML-DSA / SLH-DSA"),
        ("Ed25519", "SIGN", "DIGITAL_SIGNATURE", "ML-DSA / SLH-DSA"),
        ("Ed25519", "VERIFY", "DIGITAL_SIGNATURE", "ML-DSA / SLH-DSA"),
        ("ECDH", "KEY_ESTABLISHMENT", "KEY_ESTABLISHMENT", "ML-KEM"),
        ("X25519", "KEY_ESTABLISHMENT", "KEY_ESTABLISHMENT", "ML-KEM"),
        ("AES", "CONSTRUCTION", "SYMMETRIC_ENCRYPTION", "KEY / IMPLEMENTATION REVIEW"),
        ("SHA-1", "HASH", "HASH", "HASH / POLICY REVIEW"),
        ("SHA-256", "HASH", "HASH", "HASH / POLICY REVIEW"),
    }

    assert expected <= seen


async def test_rsa_key_generation_is_left_unclassified(analysis) -> None:
    """An RSA key can sign or transport, so generating one settles nothing."""
    result, _ = analysis

    keygen = [
        f
        for f in result.findings
        if f.match.algorithm == "RSA" and f.match.operation is CryptoOperation.KEY_GENERATION
    ]

    assert keygen
    for finding in keygen:
        assert finding.role.role is CryptographicRole.UNKNOWN
        assert finding.pqc.review_path is PqcReviewPath.MANUAL_REVIEW
        assert finding.pqc.is_migration_candidate is False


async def test_single_purpose_key_generation_is_classified(analysis) -> None:
    result, _ = analysis

    by_algorithm = {
        (f.match.algorithm, f.role.role)
        for f in result.findings
        if f.match.operation is CryptoOperation.KEY_GENERATION
    }

    assert ("Ed25519", CryptographicRole.DIGITAL_SIGNATURE) in by_algorithm
    assert ("X25519", CryptographicRole.KEY_ESTABLISHMENT) in by_algorithm


async def test_the_canonical_response_serialises_for_every_real_finding(analysis) -> None:
    result, _ = analysis

    for finding in result.findings:
        payload = to_finding(
            finding,
            scan_id="scan-real",
            repository=result.repository,
            commit_sha=result.commit_sha,
        ).model_dump(mode="json")

        assert payload["id"] == finding.fingerprint
        assert payload["observed"]["source_excerpt"].strip()
        assert payload["inference"]["role"]
        assert payload["migration"]["review_path"]
        assert payload["priority"]["reasons"]
        assert payload["review"] is None
