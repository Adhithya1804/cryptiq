"""No request leaves the process unless its host is a known GitHub host."""

import pytest

from app.errors import RepositoryUnavailableError
from app.integrations.github import validator


@pytest.mark.parametrize(
    "url",
    [
        "https://api.github.com/repos/pyca/cryptography",
        "https://codeload.github.com/pyca/cryptography/zip/abc",
        "https://objects.githubusercontent.com/archive.zip",
        "https://github.com/pyca/cryptography",
    ],
)
def test_known_github_endpoints_are_allowed(url: str) -> None:
    validator.assert_allowed_url(url)


@pytest.mark.parametrize(
    "url",
    [
        "http://api.github.com/repos/pyca/cryptography",
        "ftp://api.github.com/repo.zip",
        "file:///etc/passwd",
        "https://localhost/repo.zip",
        "https://127.0.0.1/repo.zip",
        "https://0.0.0.0/repo.zip",
        "https://10.0.0.5/repo.zip",
        "https://169.254.169.254/latest/meta-data/",
        "https://[::1]/repo.zip",
        "https://metadata.google.internal/computeMetadata/v1/",
        "https://evil.example.com/repo.zip",
        "https://api.github.com.evil.example.com/repo.zip",
        "https://githubusercontent.com.evil.example.com/repo.zip",
        "https://",
    ],
)
def test_everything_else_is_refused(url: str) -> None:
    with pytest.raises(RepositoryUnavailableError):
        validator.assert_allowed_url(url)


@pytest.mark.parametrize(
    ("host", "expected"),
    [
        ("api.github.com", True),
        ("API.GitHub.com", True),
        ("codeload.github.com.", True),
        ("release-assets.githubusercontent.com", True),
        ("raw.githubusercontent.com", True),
        ("evilgithubusercontent.com", False),
        ("gitlab.com", False),
        ("github.com.attacker.net", False),
    ],
)
def test_host_allowlist(host: str, expected: bool) -> None:
    assert validator.is_allowed_host(host) is expected


async def test_a_host_resolving_to_a_public_address_is_accepted(monkeypatch) -> None:
    monkeypatch.setattr(validator, "_resolve", lambda host: ["140.82.121.6"])

    await validator.assert_host_resolves_publicly("api.github.com")


@pytest.mark.parametrize(
    "address",
    ["127.0.0.1", "10.1.2.3", "192.168.0.1", "172.16.5.4", "169.254.169.254", "::1", "fd00::1"],
)
async def test_a_host_resolving_to_a_private_address_is_refused(monkeypatch, address: str) -> None:
    monkeypatch.setattr(validator, "_resolve", lambda host: [address])

    with pytest.raises(RepositoryUnavailableError):
        await validator.assert_host_resolves_publicly("api.github.com")


async def test_one_private_answer_among_several_is_enough_to_refuse(monkeypatch) -> None:
    monkeypatch.setattr(validator, "_resolve", lambda host: ["140.82.121.6", "127.0.0.1"])

    with pytest.raises(RepositoryUnavailableError):
        await validator.assert_host_resolves_publicly("api.github.com")


async def test_an_unresolvable_host_is_refused(monkeypatch) -> None:
    def _fail(host: str) -> list[str]:
        raise OSError("no such host")

    monkeypatch.setattr(validator, "_resolve", _fail)

    with pytest.raises(RepositoryUnavailableError):
        await validator.assert_host_resolves_publicly("api.github.com")
