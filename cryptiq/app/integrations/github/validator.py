"""Validation of GitHub URLs and of every URL Cryptiq is about to request.

Two separate jobs live here. The first turns a user-supplied repository URL
into a normalized reference, refusing anything that is not a github.com
repository page. The second is the outbound guard: no request leaves the
process, redirect included, unless its host is a known GitHub host that
resolves to public addresses.
"""

import asyncio
import ipaddress
import re
import socket
from urllib.parse import urlsplit

from app.engine.ingestion.source import RepositoryReference
from app.errors import InvalidRepositoryUrlError, RepositoryUnavailableError
from app.integrations.github.models import PROVIDER

REPOSITORY_HOST = "github.com"

# Every host Cryptiq will connect to. GitHub serves archive redirects from
# codeload and githubusercontent; nothing else is reachable.
ALLOWED_HOSTS = frozenset({"api.github.com", "github.com", "codeload.github.com"})
ALLOWED_HOST_SUFFIXES = (".githubusercontent.com",)

# GitHub's own limits: owners are 39 characters of alphanumerics and hyphens,
# repository names are 100 characters of alphanumerics, hyphen, underscore, dot.
_OWNER_PATTERN = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?$")
_NAME_PATTERN = re.compile(r"^[A-Za-z0-9_.-]{1,100}$")


def parse_repository_url(url: str) -> RepositoryReference:
    """Turn a repository URL into a normalized reference.

    Only https://github.com/{owner}/{name} is accepted, with an optional .git
    suffix and trailing slash. Any other scheme, host, port, credential, query
    or path shape is refused rather than guessed at.
    """
    candidate = url.strip()
    if not candidate:
        raise InvalidRepositoryUrlError("Repository URL is required.")

    parts = urlsplit(candidate)
    if parts.scheme != "https":
        raise InvalidRepositoryUrlError("Repository URL must use https.")
    if parts.username or parts.password:
        raise InvalidRepositoryUrlError("Repository URL must not carry credentials.")
    if parts.port is not None:
        raise InvalidRepositoryUrlError("Repository URL must not specify a port.")
    if parts.query or parts.fragment:
        raise InvalidRepositoryUrlError(
            "Repository URL must not carry a query string or fragment."
        )
    if (parts.hostname or "").lower() != REPOSITORY_HOST:
        raise InvalidRepositoryUrlError(f"Only {REPOSITORY_HOST} repositories are supported.")

    owner, name = _split_repository_path(parts.path)
    return RepositoryReference(
        provider=PROVIDER,
        owner=owner,
        name=name,
        canonical_url=f"https://{REPOSITORY_HOST}/{owner}/{name}",
    )


def _split_repository_path(path: str) -> tuple[str, str]:
    segments = [segment for segment in path.split("/") if segment]
    if len(segments) != 2:
        raise InvalidRepositoryUrlError(
            "Repository URL must be https://github.com/{owner}/{repository}."
        )

    owner, name = segments
    name = name.removesuffix(".git")

    if not _OWNER_PATTERN.match(owner):
        raise InvalidRepositoryUrlError("Repository owner is not a valid GitHub name.")
    if not _NAME_PATTERN.match(name) or name in {".", ".."}:
        raise InvalidRepositoryUrlError("Repository name is not a valid GitHub name.")
    return owner, name


def is_allowed_host(host: str) -> bool:
    """Return True if the host is one Cryptiq is permitted to contact."""
    hostname = host.lower().rstrip(".")
    if hostname in ALLOWED_HOSTS:
        return True
    return any(hostname.endswith(suffix) for suffix in ALLOWED_HOST_SUFFIXES)


def assert_allowed_url(url: str) -> None:
    """Refuse any URL that is not an https request to an allowed GitHub host.

    An IP literal is refused outright: GitHub is always reached by name, so a
    literal can only be an attempt to reach something else.
    """
    parts = urlsplit(url)
    if parts.scheme != "https":
        raise RepositoryUnavailableError("Refusing a non-https request.")
    hostname = parts.hostname or ""
    if not hostname:
        raise RepositoryUnavailableError("Refusing a request without a host.")
    if _is_ip_literal(hostname):
        raise RepositoryUnavailableError("Refusing a request to an IP address.")
    if not is_allowed_host(hostname):
        raise RepositoryUnavailableError("Refusing a request to an untrusted host.")


def _is_ip_literal(hostname: str) -> bool:
    try:
        ipaddress.ip_address(hostname.strip("[]"))
    except ValueError:
        return False
    return True


def _resolve(hostname: str) -> list[str]:
    infos = socket.getaddrinfo(hostname, 443, proto=socket.IPPROTO_TCP)
    return [info[4][0] for info in infos]


async def assert_host_resolves_publicly(hostname: str) -> None:
    """Refuse a host that resolves to anything but a public address.

    This closes the case where an allowed name is pointed at a loopback,
    private, link-local or cloud-metadata address. The socket the HTTP client
    opens is resolved separately, so this narrows the window rather than
    removing it; the host allowlist above is the primary control.
    """
    try:
        addresses = await asyncio.to_thread(_resolve, hostname)
    except OSError as exc:
        raise RepositoryUnavailableError("Could not resolve the provider host.") from exc

    if not addresses:
        raise RepositoryUnavailableError("Could not resolve the provider host.")

    for address in addresses:
        if not ipaddress.ip_address(address).is_global:
            raise RepositoryUnavailableError(
                "The provider host resolves to a non-public address."
            )
