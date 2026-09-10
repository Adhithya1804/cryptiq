"""The deterministic pipeline over a local snapshot."""

from pathlib import Path

import pytest

from app.engine.impact import ImpactNodeType, ImpactScope
from app.engine.ingestion import IngestionLimits, RepositoryReference, SourceSnapshot
from app.engine.ingestion.service import build_result
from app.engine.pipeline import analyze_snapshot
from app.engine.priority import ReviewPriority
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

IMPORT = b"from cryptography.hazmat.primitives.asymmetric import rsa\n"

TREE = {
    "src/signing.py": IMPORT
    + b"\n"
    + b"class Signer:\n"
    + b"    def sign(self, key: rsa.RSAPrivateKey, payload):\n"
    + b"        return key.sign(\n"
    + b"            payload,\n"
    + b"        )\n",
    "src/keys.py": IMPORT + b"def build():\n    return rsa.generate_private_key()\n",
    "src/unrelated.py": b"def run(thing):\n    return thing.sign(b'x')\n",
    "src/broken.py": b"def broken(:\n",
    "README.md": b"# rsa.generate_private_key\n",
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
    ingestion = build_result(snapshot, LIMITS)
    return analyze_snapshot(ingestion, root), root


def test_the_pipeline_produces_findings_with_every_stage_attached(analysis) -> None:
    result, _ = analysis

    assert result.commit_sha == COMMIT
    assert result.repository == REFERENCE
    assert [finding.match.api for finding in result.findings] == [
        "rsa.generate_private_key",
        "RSAPrivateKey.sign",
    ]
    for finding in result.findings:
        assert finding.evidence.source_excerpt
        assert finding.impact.scope is ImpactScope.STATICALLY_OBSERVED
        assert finding.priority.level in set(ReviewPriority)
        assert len(finding.fingerprint) == 64


def test_the_evidence_quotes_the_exact_ast_span(analysis) -> None:
    result, _ = analysis

    signing = next(f for f in result.findings if f.match.api == "RSAPrivateKey.sign")
    assert signing.evidence.start_line == 5
    assert signing.evidence.end_line == 7
    assert signing.evidence.source_excerpt.splitlines() == [
        "        return key.sign(",
        "            payload,",
        "        )",
    ]
    assert signing.evidence.repository_sha == COMMIT
    assert signing.evidence.rule_id == "PY-CRYPTO-RSA"
    assert signing.evidence.parser_version == "python-ast-1"


def test_the_impact_reaches_the_enclosing_class_and_module(analysis) -> None:
    result, _ = analysis

    signing = next(f for f in result.findings if f.match.api == "RSAPrivateKey.sign")
    labels = {node.node_type: node.label for node in signing.impact.nodes}
    assert labels[ImpactNodeType.CLASS] == "Signer"
    assert labels[ImpactNodeType.MODULE] == "src.signing"
    assert labels[ImpactNodeType.FILE] == "src/signing.py"


def test_priority_reasons_are_attached(analysis) -> None:
    result, _ = analysis

    for finding in result.findings:
        assert finding.priority.reasons
        assert any("Shor" in reason for reason in finding.priority.reasons)


def test_a_broken_file_is_counted_but_does_not_stop_the_pipeline(analysis) -> None:
    result, _ = analysis

    assert result.failed_files == 1
    assert result.parsed_files == 3
    assert result.total_files == len(TREE)


def test_the_pipeline_is_deterministic(tmp_path: Path) -> None:
    def run(where: Path):
        root = write_tree(where, TREE)
        snapshot = SourceSnapshot(
            root_path=root,
            repository=REFERENCE,
            commit_sha=COMMIT,
            content_hash="0" * 64,
            file_count=len(TREE),
        )
        return analyze_snapshot(build_result(snapshot, LIMITS), root)

    first = run(tmp_path / "one")
    second = run(tmp_path / "two")

    assert [f.fingerprint for f in first.findings] == [f.fingerprint for f in second.findings]
    assert [f.priority for f in first.findings] == [f.priority for f in second.findings]
    assert [f.impact for f in first.findings] == [f.impact for f in second.findings]
    assert [f.evidence for f in first.findings] == [f.evidence for f in second.findings]


def test_a_finding_whose_source_cannot_be_read_is_dropped(tmp_path: Path) -> None:
    root = write_tree(tmp_path / "snapshot", TREE)
    snapshot = SourceSnapshot(
        root_path=root,
        repository=REFERENCE,
        commit_sha=COMMIT,
        content_hash="0" * 64,
        file_count=len(TREE),
    )
    ingestion = build_result(snapshot, LIMITS)
    (root / "src" / "keys.py").unlink()

    result = analyze_snapshot(ingestion, root)

    assert [finding.match.file_path for finding in result.findings] == ["src/signing.py"]


def test_the_fingerprint_ignores_lines_moving(tmp_path: Path) -> None:
    """Inserting a line above a call must not change the finding's identity."""
    shifted = dict(TREE)
    shifted["src/keys.py"] = IMPORT + b"\n# a new comment\n\ndef build():\n    return rsa.generate_private_key()\n"

    def run(where: Path, tree: dict[str, bytes]):
        root = write_tree(where, tree)
        snapshot = SourceSnapshot(
            root_path=root,
            repository=REFERENCE,
            commit_sha=COMMIT,
            content_hash="0" * 64,
            file_count=len(tree),
        )
        return analyze_snapshot(build_result(snapshot, LIMITS), root)

    before = run(tmp_path / "before", TREE)
    after = run(tmp_path / "after", shifted)

    keys_before = next(f for f in before.findings if f.match.file_path == "src/keys.py")
    keys_after = next(f for f in after.findings if f.match.file_path == "src/keys.py")

    assert keys_after.match.location.start_line != keys_before.match.location.start_line
    assert keys_after.fingerprint == keys_before.fingerprint


def test_two_identical_calls_in_one_function_share_a_fingerprint(tmp_path: Path) -> None:
    """Identity is not positional, so repeated identical calls collapse.

    This is the intended trade-off: it is what lets a finding survive an edit
    and be reported as UNCHANGED. The consequence is that a fingerprint is not
    unique per call site, so anything persisting findings under
    ``UNIQUE(scan_id, fingerprint)`` must deduplicate rather than insert both.
    """
    tree = {
        "src/twice.py": IMPORT
        + b"def build():\n"
        + b"    first = rsa.generate_private_key()\n"
        + b"    second = rsa.generate_private_key()\n"
        + b"    return first, second\n"
    }
    root = write_tree(tmp_path / "snapshot", tree)
    snapshot = SourceSnapshot(
        root_path=root,
        repository=REFERENCE,
        commit_sha=COMMIT,
        content_hash="0" * 64,
        file_count=1,
    )

    result = analyze_snapshot(build_result(snapshot, LIMITS), root)

    assert len(result.findings) == 2
    assert result.findings[0].match.location.start_line != (
        result.findings[1].match.location.start_line
    )
    assert result.findings[0].fingerprint == result.findings[1].fingerprint


def test_a_call_moved_to_another_function_gets_a_new_identity(tmp_path: Path) -> None:
    def run(where: Path, function_name: str) -> str:
        tree = {
            "src/moved.py": IMPORT
            + f"def {function_name}():\n    return rsa.generate_private_key()\n".encode()
        }
        root = write_tree(where, tree)
        snapshot = SourceSnapshot(
            root_path=root,
            repository=REFERENCE,
            commit_sha=COMMIT,
            content_hash="0" * 64,
            file_count=1,
        )
        return analyze_snapshot(build_result(snapshot, LIMITS), root).findings[0].fingerprint

    assert run(tmp_path / "a", "build") != run(tmp_path / "b", "make")
