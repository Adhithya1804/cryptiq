"""Opt-in RSA detection against a real repository at an exact commit.

Enable with CRYPTIQ_RUN_NETWORK_TESTS=1. The rest of the suite must never
depend on GitHub being reachable, so this module skips by default.
"""

import os

import pytest

from app.engine.ingestion import ingest_commit
from app.engine.parser import parse_all
from app.engine.rules import CryptoOperation, MatchConfidence, RsaRule, evaluate_files
from app.integrations.github import GitHubSourceProvider, parse_repository_url

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
async def rsa_matches():
    """Ingest the exact commit once, parse it, and run only the RSA rule."""
    repository = parse_repository_url(REPOSITORY_URL)
    async with ingest_commit(GitHubSourceProvider(), repository, COMMIT_SHA) as result:
        parsed = parse_all(result.snapshot.root_path, result.discovered_files)
        sources = {file.path: file for file in parsed}
        yield evaluate_files(parsed, rules=[RsaRule()]), sources


async def test_real_rsa_usage_is_found(rsa_matches) -> None:
    matches, _ = rsa_matches

    assert matches
    assert len({match.file_path for match in matches}) > 1
    # Every operation the RSA rule knows about is exercised by this commit.
    # The engine's vocabulary is wider; the other members belong to the rules
    # this test deliberately does not run.
    assert {match.operation for match in matches} == {
        CryptoOperation.KEY_GENERATION,
        CryptoOperation.SIGN,
        CryptoOperation.VERIFY,
        CryptoOperation.ENCRYPT,
        CryptoOperation.DECRYPT,
    }


async def test_every_observation_is_a_well_formed_rsa_record(rsa_matches) -> None:
    matches, sources = rsa_matches

    for match in matches:
        assert match.rule_id == "PY-CRYPTO-RSA"
        assert match.algorithm == "RSA"
        assert match.primitive == "RSA"
        assert match.library == "cryptography"
        assert match.api
        assert isinstance(match.operation, CryptoOperation)
        assert isinstance(match.confidence, MatchConfidence)
        assert match.confidence is not MatchConfidence.UNKNOWN
        assert match.file_path in sources
        assert not match.file_path.startswith("/")
        assert 1 <= match.location.start_line <= match.location.end_line
        assert match.location.start_column >= 0


async def test_the_api_always_names_a_known_rsa_entry_point(rsa_matches) -> None:
    matches, _ = rsa_matches
    permitted = {
        "rsa.generate_private_key",
        "RSAPrivateKey.sign",
        "RSAPrivateKey.decrypt",
        "RSAPublicKey.verify",
        "RSAPublicKey.encrypt",
    }

    assert {match.api for match in matches} <= permitted


async def test_no_diffie_hellman_key_generation_is_claimed_as_rsa(rsa_matches) -> None:
    matches, sources = rsa_matches

    for match in matches:
        parsed = sources[match.file_path]
        call = next(call for call in parsed.calls if call.node is match.node)
        assert call.chain is not None
        root = call.chain[0]
        resolved = parsed.resolve(root)
        # Either the callable itself resolves into the RSA namespace, or the
        # receiver was established locally. A bare "parameters" or "param"
        # receiver from a Diffie-Hellman test satisfies neither.
        assert resolved is not None or root not in {"param", "parameters", "params"}


async def test_dh_generate_private_key_call_sites_exist_but_are_not_reported(
    rsa_matches,
) -> None:
    matches, sources = rsa_matches
    reported = {(match.file_path, match.location.start_line) for match in matches}

    dh_sites = [
        (file.path, call.location.start_line)
        for file in sources.values()
        for call in file.calls
        if call.attribute == "generate_private_key"
        and call.chain is not None
        and file.resolve(call.chain[0]) is None
    ]

    assert dh_sites
    assert not (set(dh_sites) & reported)


async def test_the_result_is_deterministic(rsa_matches) -> None:
    matches, sources = rsa_matches

    again = evaluate_files(sources.values(), rules=[RsaRule()])
    assert again == matches
    assert [match.sort_key for match in matches] == sorted(
        match.sort_key for match in matches
    )
