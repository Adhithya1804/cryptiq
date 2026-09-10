"""GitHub implementation of the SourceProvider protocol.

Nothing here is imported by the engine. Cryptiq never fetches a URL the user
supplied: every request is built from a validated owner, repository name and
verified commit SHA, and every hop is checked against the host allowlist in
validator.py before the connection is made.
"""

import logging
import shutil
import tempfile
from pathlib import Path
from urllib.parse import quote, urljoin, urlsplit

import httpx

from app.config import Settings, get_settings
from app.engine.ingestion.archive import extract_zip
from app.engine.ingestion.limits import IngestionLimits
from app.engine.ingestion.source import (
    RepositoryReference,
    SourceSnapshot,
    compute_content_hash,
    count_files,
)
from app.engine.ingestion.validation import normalize_commit_sha, normalize_full_commit_sha
from app.errors import (
    CommitNotFoundError,
    RepositoryNotFoundError,
    RepositoryUnavailableError,
    UnsupportedProviderError,
)
from app.integrations.github import validator
from app.integrations.github.models import PROVIDER, GitHubCommit

logger = logging.getLogger(__name__)

WORKSPACE_PREFIX = "cryptiq-source-"
ARCHIVE_PREFIX = "cryptiq-archive-"
MAX_REDIRECTS = 5
API_VERSION = "2022-11-28"
USER_AGENT = "cryptiq/0.1.0"

_RATE_LIMITED = frozenset({403, 429})


class GitHubSourceProvider:
    """Retrieves an exact commit from GitHub as a source snapshot."""

    def __init__(
        self,
        settings: Settings | None = None,
        limits: IngestionLimits | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._settings = settings or get_settings()
        self._limits = limits or IngestionLimits.from_settings(self._settings)
        self._transport = transport
        self._api_base = self._settings.github_api_url.rstrip("/")
        self._api_host = (urlsplit(self._api_base).hostname or "").lower()

    async def fetch_commit(
        self,
        repository: RepositoryReference,
        commit_sha: str,
    ) -> SourceSnapshot:
        """Return a snapshot of exactly the requested revision.

        The SHA is resolved and verified through the API first, so the archive
        is always addressed by full SHA and never by a branch or tag.
        """
        if repository.provider != PROVIDER:
            raise UnsupportedProviderError(
                f"Provider {repository.provider!r} is not supported."
            )

        requested = normalize_commit_sha(commit_sha)

        async with self._client() as client:
            resolved_sha = await self._resolve_commit(client, repository, requested)
            workspace = Path(tempfile.mkdtemp(prefix=WORKSPACE_PREFIX))
            try:
                await self._download_and_extract(client, repository, resolved_sha, workspace)
            except BaseException:
                shutil.rmtree(workspace, ignore_errors=True)
                raise

        file_count = count_files(workspace)
        snapshot = SourceSnapshot(
            root_path=workspace,
            repository=repository,
            commit_sha=resolved_sha,
            content_hash=compute_content_hash(workspace),
            file_count=file_count,
        )
        logger.info(
            "retrieved %s at %s: %d files", repository.slug, resolved_sha, file_count
        )
        return snapshot

    def _client(self) -> httpx.AsyncClient:
        """Return a client that never follows a redirect on its own."""
        return httpx.AsyncClient(
            timeout=httpx.Timeout(self._settings.github_timeout_seconds),
            follow_redirects=False,
            transport=self._transport,
        )

    def _api_url(self, *segments: str) -> str:
        path = "/".join(quote(segment, safe="") for segment in segments)
        return f"{self._api_base}/{path}"

    def _headers(self, url: str) -> dict[str, str]:
        """Return request headers, sending the token only to the API host.

        A redirect leaves GitHub's API for codeload, so the Authorization
        header is dropped on any other host rather than handed to it.
        """
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": API_VERSION,
            "User-Agent": USER_AGENT,
        }
        token = self._settings.github_token
        if token and (urlsplit(url).hostname or "").lower() == self._api_host:
            headers["Authorization"] = f"Bearer {token}"
        return headers

    async def _request(self, client: httpx.AsyncClient, url: str) -> httpx.Response:
        validator.assert_allowed_url(url)
        await validator.assert_host_resolves_publicly(urlsplit(url).hostname or "")
        try:
            return await client.get(url, headers=self._headers(url))
        except httpx.HTTPError as exc:
            # The exception text can carry the full request URL; only the type
            # is safe to record.
            logger.warning("GitHub request failed: %s", type(exc).__name__)
            raise RepositoryUnavailableError("The provider could not be reached.") from exc

    async def _resolve_commit(
        self,
        client: httpx.AsyncClient,
        repository: RepositoryReference,
        requested: str,
    ) -> str:
        """Resolve the requested SHA to a verified full 40-character SHA."""
        url = self._api_url("repos", repository.owner, repository.name, "commits", requested)
        response = await self._request(client, url)

        if response.status_code in {404, 422}:
            await self._raise_missing(client, repository)
        self._raise_for_status(response)

        try:
            payload = response.json()
        except ValueError as exc:
            raise RepositoryUnavailableError(
                "The provider returned an unreadable commit response."
            ) from exc

        resolved = normalize_full_commit_sha(GitHubCommit.from_payload(payload).sha)
        if not resolved.startswith(requested):
            raise RepositoryUnavailableError(
                "The provider returned a different revision than the one requested."
            )
        return resolved

    async def _raise_missing(
        self, client: httpx.AsyncClient, repository: RepositoryReference
    ) -> None:
        """Distinguish a missing repository from a missing commit."""
        url = self._api_url("repos", repository.owner, repository.name)
        response = await self._request(client, url)
        if response.status_code == 404:
            raise RepositoryNotFoundError(
                f"Repository {repository.slug} was not found."
            )
        raise CommitNotFoundError(
            f"Commit was not found in {repository.slug}."
        )

    def _raise_for_status(self, response: httpx.Response) -> None:
        """Map an unsuccessful response onto a domain error, never a body."""
        if response.is_success:
            return
        if response.status_code in _RATE_LIMITED:
            raise RepositoryUnavailableError(
                "The provider refused the request; it may be rate limited."
            )
        if response.status_code == 404:
            raise CommitNotFoundError("The requested revision was not found.")
        raise RepositoryUnavailableError(
            f"The provider responded with status {response.status_code}."
        )

    async def _download_and_extract(
        self,
        client: httpx.AsyncClient,
        repository: RepositoryReference,
        resolved_sha: str,
        workspace: Path,
    ) -> None:
        """Download the archive for the exact SHA and extract it into workspace."""
        url = self._api_url(
            "repos", repository.owner, repository.name, "zipball", resolved_sha
        )
        with tempfile.NamedTemporaryFile(prefix=ARCHIVE_PREFIX, suffix=".zip") as handle:
            archive_path = Path(handle.name)
            await self._download(client, url, archive_path)
            extract_zip(archive_path, workspace, self._limits)

    async def _download(self, client: httpx.AsyncClient, url: str, destination: Path) -> None:
        """Stream an archive to disk, validating every redirect hop itself."""
        current = url
        for _ in range(MAX_REDIRECTS + 1):
            validator.assert_allowed_url(current)
            await validator.assert_host_resolves_publicly(urlsplit(current).hostname or "")
            try:
                async with client.stream(
                    "GET", current, headers=self._headers(current)
                ) as response:
                    if response.is_redirect:
                        current = self._next_hop(current, response)
                        continue
                    self._raise_for_status(response)
                    await self._write_stream(response, destination)
                    return
            except httpx.HTTPError as exc:
                logger.warning("GitHub archive download failed: %s", type(exc).__name__)
                raise RepositoryUnavailableError(
                    "The provider could not be reached."
                ) from exc

        raise RepositoryUnavailableError("The provider redirected too many times.")

    def _next_hop(self, current: str, response: httpx.Response) -> str:
        location = response.headers.get("location")
        if not location:
            raise RepositoryUnavailableError("The provider sent a redirect without a target.")
        return urljoin(current, location)

    async def _write_stream(self, response: httpx.Response, destination: Path) -> None:
        downloaded = 0
        with destination.open("wb") as sink:
            async for chunk in response.aiter_bytes():
                downloaded += len(chunk)
                self._limits.check_archive_bytes(downloaded)
                sink.write(chunk)

