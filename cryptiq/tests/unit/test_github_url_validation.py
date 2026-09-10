"""Only a github.com repository page is accepted as a repository URL."""

import pytest

from app.errors import InvalidRepositoryUrlError
from app.integrations.github.validator import parse_repository_url


def test_valid_repository_url_is_normalized() -> None:
    reference = parse_repository_url("https://github.com/pyca/cryptography")

    assert reference.provider == "github"
    assert reference.owner == "pyca"
    assert reference.name == "cryptography"
    assert reference.canonical_url == "https://github.com/pyca/cryptography"
    assert reference.slug == "pyca/cryptography"


@pytest.mark.parametrize(
    "url",
    [
        "https://github.com/pyca/cryptography/",
        "https://github.com/pyca/cryptography.git",
        "  https://github.com/pyca/cryptography  ",
        "https://GitHub.com/pyca/cryptography",
    ],
)
def test_accepted_variants_normalize_to_the_same_reference(url: str) -> None:
    assert parse_repository_url(url).canonical_url == "https://github.com/pyca/cryptography"


@pytest.mark.parametrize(
    "url",
    [
        "http://github.com/pyca/cryptography",
        "ftp://github.com/pyca/cryptography",
        "file:///etc/passwd",
        "git://github.com/pyca/cryptography",
        "//github.com/pyca/cryptography",
    ],
)
def test_non_https_schemes_are_rejected(url: str) -> None:
    with pytest.raises(InvalidRepositoryUrlError):
        parse_repository_url(url)


@pytest.mark.parametrize(
    "url",
    [
        "https://localhost/pyca/cryptography",
        "https://127.0.0.1/pyca/cryptography",
        "https://0.0.0.0/pyca/cryptography",
        "https://10.0.0.5/pyca/cryptography",
        "https://192.168.1.10/pyca/cryptography",
        "https://172.16.0.1/pyca/cryptography",
        "https://169.254.169.254/pyca/cryptography",
        "https://[::1]/pyca/cryptography",
        "https://metadata.google.internal/pyca/cryptography",
        "https://evil.example.com/pyca/cryptography",
        "https://github.com.evil.example.com/pyca/cryptography",
        "https://notgithub.com/pyca/cryptography",
    ],
)
def test_non_github_hosts_are_rejected(url: str) -> None:
    with pytest.raises(InvalidRepositoryUrlError):
        parse_repository_url(url)


@pytest.mark.parametrize(
    "url",
    [
        "https://user:token@github.com/pyca/cryptography",
        "https://github.com:8443/pyca/cryptography",
        "https://github.com/pyca/cryptography?tab=readme",
        "https://github.com/pyca/cryptography#readme",
    ],
)
def test_credentials_ports_and_query_strings_are_rejected(url: str) -> None:
    with pytest.raises(InvalidRepositoryUrlError):
        parse_repository_url(url)


@pytest.mark.parametrize(
    "url",
    [
        "",
        "   ",
        "https://github.com/",
        "https://github.com/pyca",
        "https://github.com/pyca/cryptography/tree/main",
        "https://github.com/pyca/../etc/passwd",
        "https://github.com/pyca/..",
        "https://github.com/-bad/cryptography",
        "https://github.com/pyca/crypto graphy",
        f"https://github.com/pyca/{'x' * 101}",
    ],
)
def test_malformed_repository_paths_are_rejected(url: str) -> None:
    with pytest.raises(InvalidRepositoryUrlError):
        parse_repository_url(url)
