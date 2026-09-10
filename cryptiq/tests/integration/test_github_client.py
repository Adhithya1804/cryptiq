"""The GitHub provider retrieves an exact revision and nothing else."""

import json
import shutil
from pathlib import Path

import httpx
import pytest

from app.config import Settings
from app.engine.ingestion import IngestionLimits, RepositoryReference
from app.errors import (
    ArchiveTooLargeError,
    CommitNotFoundError,
    RepositoryNotFoundError,
    RepositoryUnavailableError,
    UnsafeArchiveError,
    UnsupportedProviderError,
)
from app.integrations.github import client as client_module
from app.integrations.github import validator
from app.integrations.github.client import GitHubSourceProvider
from tests.support import build_raw_zip, build_zip

FULL_SHA = "1f903f5ed2e5e316f345a927555e48535829d8de"
SHORT_SHA = "1f903f5"
ARCHIVE_URL = f"https://api.github.com/repos/pyca/cryptography/zipball/{FULL_SHA}"
CODELOAD_URL = f"https://codeload.github.com/pyca/cryptography/legacy.zip/{FULL_SHA}"

REFERENCE = RepositoryReference(
    provider="github",
    owner="pyca",
    name="cryptography",
    canonical_url="https://github.com/pyca/cryptography",
)

LIMITS = IngestionLimits(
    max_archive_bytes=1024 * 1024,
    max_extracted_bytes=1024 * 1024,
    max_files=100,
    max_file_bytes=64 * 1024,
)

ARCHIVE = build_zip({"src/keys.py": b"x = 1\n", "README.md": b"# hi\n"})


@pytest.fixture(autouse=True)
def _no_dns(monkeypatch) -> None:
    """Keep the unit-level provider tests off the network."""
    monkeypatch.setattr(validator, "_resolve", lambda host: ["140.82.121.6"])


def _settings(**overrides: object) -> Settings:
    return Settings(_env_file=None, **overrides)


def _provider(
    handler, limits: IngestionLimits = LIMITS, **setting_overrides: object
) -> GitHubSourceProvider:
    return GitHubSourceProvider(
        settings=_settings(**setting_overrides),
        limits=limits,
        transport=httpx.MockTransport(handler),
    )


def _commit_response(sha: str = FULL_SHA) -> httpx.Response:
    return httpx.Response(200, content=json.dumps({"sha": sha}), headers={"content-type": "application/json"})


def _default_handler(
    *,
    commit: httpx.Response | None = None,
    archive: bytes = ARCHIVE,
    seen: list[httpx.Request] | None = None,
):
    def handler(request: httpx.Request) -> httpx.Response:
        if seen is not None:
            seen.append(request)
        path = request.url.path
        if "/zipball/" in path:
            return httpx.Response(302, headers={"location": CODELOAD_URL})
        if request.url.host == "codeload.github.com":
            return httpx.Response(200, content=archive)
        if "/commits/" in path:
            return commit or _commit_response()
        return httpx.Response(200, content=json.dumps({"full_name": "pyca/cryptography"}))

    return handler


async def test_a_full_sha_is_retrieved_and_verified() -> None:
    provider = _provider(_default_handler())

    snapshot = await provider.fetch_commit(REFERENCE, FULL_SHA)

    try:
        assert snapshot.commit_sha == FULL_SHA
        assert snapshot.file_count == 2
        assert (snapshot.root_path / "src" / "keys.py").read_bytes() == b"x = 1\n"
        assert len(snapshot.content_hash) == 64
    finally:
        _cleanup(snapshot.root_path)


async def test_a_short_sha_is_resolved_to_the_full_sha() -> None:
    provider = _provider(_default_handler())

    snapshot = await provider.fetch_commit(REFERENCE, SHORT_SHA)

    try:
        assert snapshot.commit_sha == FULL_SHA
    finally:
        _cleanup(snapshot.root_path)


async def test_the_archive_is_requested_by_full_sha_only() -> None:
    seen: list[httpx.Request] = []
    provider = _provider(_default_handler(seen=seen))

    snapshot = await provider.fetch_commit(REFERENCE, SHORT_SHA)
    _cleanup(snapshot.root_path)

    archive_requests = [request for request in seen if "/zipball/" in request.url.path]
    assert [str(request.url) for request in archive_requests] == [ARCHIVE_URL]
    assert not any("refs/heads" in str(request.url) for request in seen)


async def test_a_returned_revision_that_differs_is_rejected() -> None:
    provider = _provider(_default_handler(commit=_commit_response("b" * 40)))

    with pytest.raises(RepositoryUnavailableError):
        await provider.fetch_commit(REFERENCE, FULL_SHA)


async def test_a_returned_branch_head_is_rejected_for_a_short_sha() -> None:
    provider = _provider(_default_handler(commit=_commit_response("c" * 40)))

    with pytest.raises(RepositoryUnavailableError):
        await provider.fetch_commit(REFERENCE, SHORT_SHA)


async def test_a_missing_commit_in_an_existing_repository() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if "/commits/" in request.url.path:
            return httpx.Response(404, content=b'{"message": "No commit found"}')
        return httpx.Response(200, content=json.dumps({"full_name": "pyca/cryptography"}))

    with pytest.raises(CommitNotFoundError):
        await _provider(handler).fetch_commit(REFERENCE, FULL_SHA)


async def test_a_missing_repository() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, content=b'{"message": "Not Found"}')

    with pytest.raises(RepositoryNotFoundError):
        await _provider(handler).fetch_commit(REFERENCE, FULL_SHA)


async def test_rate_limiting_is_reported_as_unavailable() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, content=b'{"message": "API rate limit exceeded"}')

    with pytest.raises(RepositoryUnavailableError):
        await _provider(handler).fetch_commit(REFERENCE, FULL_SHA)


async def test_a_transport_failure_is_reported_as_unavailable() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused to https://api.github.com/secret")

    with pytest.raises(RepositoryUnavailableError) as error:
        await _provider(handler).fetch_commit(REFERENCE, FULL_SHA)

    assert "secret" not in str(error.value)


async def test_an_unreadable_commit_payload_is_reported_as_unavailable() -> None:
    provider = _provider(
        _default_handler(commit=httpx.Response(200, content=b"not json", headers={"content-type": "application/json"}))
    )

    with pytest.raises(RepositoryUnavailableError):
        await provider.fetch_commit(REFERENCE, FULL_SHA)


async def test_a_redirect_off_github_is_refused() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if "/zipball/" in request.url.path:
            return httpx.Response(302, headers={"location": "https://evil.example.com/payload.zip"})
        return _commit_response()

    with pytest.raises(RepositoryUnavailableError):
        await _provider(handler).fetch_commit(REFERENCE, FULL_SHA)


async def test_a_redirect_to_a_loopback_address_is_refused() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if "/zipball/" in request.url.path:
            return httpx.Response(302, headers={"location": "https://127.0.0.1/payload.zip"})
        return _commit_response()

    with pytest.raises(RepositoryUnavailableError):
        await _provider(handler).fetch_commit(REFERENCE, FULL_SHA)


async def test_a_redirect_loop_is_refused() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "codeload.github.com" or "/zipball/" in request.url.path:
            return httpx.Response(302, headers={"location": CODELOAD_URL})
        return _commit_response()

    with pytest.raises(RepositoryUnavailableError):
        await _provider(handler).fetch_commit(REFERENCE, FULL_SHA)


async def test_the_token_is_sent_to_the_api_and_never_to_the_archive_host() -> None:
    seen: list[httpx.Request] = []
    provider = _provider(_default_handler(seen=seen), github_token="super-secret-token")

    snapshot = await provider.fetch_commit(REFERENCE, FULL_SHA)
    _cleanup(snapshot.root_path)

    api_requests = [r for r in seen if r.url.host == "api.github.com"]
    codeload_requests = [r for r in seen if r.url.host == "codeload.github.com"]
    assert all(r.headers.get("authorization") == "Bearer super-secret-token" for r in api_requests)
    assert codeload_requests
    assert all("authorization" not in r.headers for r in codeload_requests)


async def test_an_oversized_archive_is_refused() -> None:
    provider = _provider(
        _default_handler(archive=b"a" * 4096),
        limits=IngestionLimits(
            max_archive_bytes=1024,
            max_extracted_bytes=1024 * 1024,
            max_files=100,
            max_file_bytes=1024,
        ),
    )

    with pytest.raises(ArchiveTooLargeError):
        await provider.fetch_commit(REFERENCE, FULL_SHA)


async def test_an_unsafe_archive_is_refused_and_leaves_no_directory_behind(
    monkeypatch, tmp_path: Path
) -> None:
    workspace = tmp_path / "workspace"
    monkeypatch.setattr(client_module.tempfile, "mkdtemp", lambda prefix: str(_made(workspace)))
    provider = _provider(_default_handler(archive=build_raw_zip(["../escape.py"])))

    with pytest.raises(UnsafeArchiveError):
        await provider.fetch_commit(REFERENCE, FULL_SHA)

    assert not workspace.exists()
    assert not (tmp_path / "escape.py").exists()


def _made(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


async def test_a_non_github_reference_is_refused() -> None:
    reference = RepositoryReference(
        provider="gitlab",
        owner="pyca",
        name="cryptography",
        canonical_url="https://gitlab.com/pyca/cryptography",
    )

    with pytest.raises(UnsupportedProviderError):
        await _provider(_default_handler()).fetch_commit(reference, FULL_SHA)


def _cleanup(root: Path) -> None:
    shutil.rmtree(root, ignore_errors=True)
