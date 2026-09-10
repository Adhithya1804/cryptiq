"""HTTP client for the Cryptiq CLI.

One small wrapper around :class:`httpx.Client` that speaks the ``/api/v1``
contract. It adds nothing to the responses -- callers get the parsed JSON body
exactly as the API returned it -- and it turns transport and HTTP errors into
:class:`CliError`, which carries the process exit code to use.
"""

from __future__ import annotations

import os
from typing import Any, Self

import httpx

#: Exit codes, shared with :mod:`app.cli.main`.
EXIT_OK = 0
EXIT_FAILURE = 1
EXIT_USAGE = 2
EXIT_SCAN_FAILED = 3
EXIT_NOT_FOUND = 4

DEFAULT_API_URL = "http://localhost:8000/api/v1"
DEFAULT_TIMEOUT = 30.0


class CliError(Exception):
    """A user-facing failure. ``exit_code`` is the process status to exit with."""

    def __init__(self, message: str, *, exit_code: int = EXIT_FAILURE) -> None:
        super().__init__(message)
        self.message = message
        self.exit_code = exit_code


def resolve_api_url(explicit: str | None) -> str:
    """Pick the API base URL: flag, then ``CRYPTIQ_API_URL``, then the default."""
    url = explicit or os.environ.get("CRYPTIQ_API_URL") or DEFAULT_API_URL
    return url.rstrip("/")


class CryptiqClient:
    """A synchronous client for the endpoints the CLI needs."""

    def __init__(
        self,
        base_url: str | None = None,
        *,
        timeout: float = DEFAULT_TIMEOUT,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.base_url = resolve_api_url(base_url)
        self._client = httpx.Client(
            base_url=self.base_url, timeout=timeout, transport=transport
        )

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    def close(self) -> None:
        self._client.close()

    # -- transport -----------------------------------------------------------

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
    ) -> Any:
        try:
            response = self._client.request(
                method, path, params=_clean_params(params), json=json
            )
        except httpx.ConnectError as exc:  # backend not running / wrong URL
            raise CliError(
                f"Could not reach the Cryptiq API at {self.base_url}. "
                "Is the backend running? "
                "(uvicorn app.main:app --port 8000)",
                exit_code=EXIT_FAILURE,
            ) from exc
        except httpx.HTTPError as exc:
            raise CliError(
                f"Request to {self.base_url}{path} failed: {exc}",
                exit_code=EXIT_FAILURE,
            ) from exc

        if response.status_code >= 400:
            raise _http_error(response)
        if not response.content:
            return None
        return response.json()

    # -- endpoints ---------------------------------------------------------

    def create_scan(self, repository_url: str, commit_sha: str) -> tuple[dict, bool]:
        """POST /scans. Returns ``(inspection, cached)``.

        ``cached`` is read from the HTTP status the API uses to signal it: 200
        when an identical completed scan was reused, 202 when a fresh scan was
        queued.
        """
        try:
            response = self._client.post(
                "/scans",
                json={"repository_url": repository_url, "commit_sha": commit_sha},
            )
        except httpx.ConnectError as exc:
            raise CliError(
                f"Could not reach the Cryptiq API at {self.base_url}. "
                "Is the backend running?",
                exit_code=EXIT_FAILURE,
            ) from exc
        if response.status_code >= 400:
            raise _http_error(response)
        cached = response.status_code == 200
        return response.json(), cached

    def get_scan(self, scan_id: str) -> dict:
        return self._request("GET", f"/scans/{scan_id}")

    def list_findings(self, scan_id: str, **params: Any) -> dict:
        return self._request("GET", f"/scans/{scan_id}/findings", params=params)

    def get_finding(self, finding_id: str) -> dict:
        return self._request("GET", f"/findings/{finding_id}")

    def review_queue(self, **params: Any) -> dict:
        return self._request("GET", "/review-queue", params=params)

    def update_review_item(self, review_id: str, body: dict[str, Any]) -> dict:
        return self._request("PATCH", f"/review-items/{review_id}", json=body)

    def get_migration_assessment(
        self, finding_id: str, domain: str | None = None
    ) -> dict[str, Any]:
        params = {"domain": domain} if domain else None
        return self._request("GET", f"/findings/{finding_id}/migration-assessment", params=params)

    def health(self) -> dict:
        return self._request("GET", "/health")


def _clean_params(params: dict[str, Any] | None) -> dict[str, Any] | None:
    if not params:
        return None
    return {key: value for key, value in params.items() if value is not None}


def _http_error(response: httpx.Response) -> CliError:
    """Turn a >=400 response into a CliError, never leaking a traceback."""
    code = response.status_code
    message = _safe_message(response)
    if code == 404:
        return CliError(message or "Resource not found.", exit_code=EXIT_NOT_FOUND)
    if code in (400, 409, 422):
        return CliError(message or "The request was rejected.", exit_code=EXIT_FAILURE)
    return CliError(
        message or f"The API returned HTTP {code}.", exit_code=EXIT_FAILURE
    )


def _safe_message(response: httpx.Response) -> str:
    try:
        payload = response.json()
    except ValueError:
        return ""
    if isinstance(payload, dict):
        error = payload.get("error")
        if isinstance(error, dict) and isinstance(error.get("message"), str):
            return error["message"]
        if isinstance(payload.get("detail"), str):
            return payload["detail"]
    return ""
