"""Application error types and the handlers that render them as JSON.

Responses carry a stable machine-readable code and a safe message. Tracebacks
and internal exception text are never sent to clients.
"""

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger(__name__)


class CryptiqError(Exception):
    """Base class for errors that are safe to report to a client."""

    status_code: int = 500
    code: str = "internal_error"

    def __init__(self, message: str, *, code: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        if code is not None:
            self.code = code


class NotFoundError(CryptiqError):
    status_code = 404
    code = "not_found"


class ValidationError(CryptiqError):
    status_code = 422
    code = "validation_error"


class IngestionError(CryptiqError):
    """Base class for failures while acquiring a source snapshot.

    Every subclass carries a stable code and a message written for a client.
    External failures are mapped onto these before they leave the ingestion
    layer, so no HTTP body, token or filesystem path reaches a response.
    """

    status_code = 502
    code = "INGESTION_FAILED"


class InvalidRepositoryUrlError(IngestionError):
    status_code = 422
    code = "INVALID_REPOSITORY_URL"


class InvalidCommitShaError(IngestionError):
    status_code = 422
    code = "INVALID_COMMIT_SHA"


class UnsupportedProviderError(IngestionError):
    status_code = 422
    code = "UNSUPPORTED_PROVIDER"


class RepositoryNotFoundError(IngestionError):
    status_code = 404
    code = "REPOSITORY_NOT_FOUND"


class CommitNotFoundError(IngestionError):
    status_code = 404
    code = "COMMIT_NOT_FOUND"


class RepositoryUnavailableError(IngestionError):
    status_code = 502
    code = "REPOSITORY_UNAVAILABLE"


class ArchiveTooLargeError(IngestionError):
    """A limit from the settings was exceeded while downloading or extracting."""

    status_code = 413
    code = "ARCHIVE_TOO_LARGE"


class UnsafeArchiveError(IngestionError):
    """An archive entry tried to escape the extraction root."""

    status_code = 422
    code = "UNSAFE_ARCHIVE"


class MalformedArchiveError(IngestionError):
    status_code = 422
    code = "MALFORMED_ARCHIVE"


def _error_response(status_code: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"error": {"code": code, "message": message}},
    )


def register_error_handlers(app: FastAPI) -> None:
    """Attach the JSON error handlers to the application."""

    @app.exception_handler(CryptiqError)
    async def handle_cryptiq_error(_: Request, exc: CryptiqError) -> JSONResponse:
        return _error_response(exc.status_code, exc.code, exc.message)

    @app.exception_handler(StarletteHTTPException)
    async def handle_http_error(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        return _error_response(exc.status_code, "http_error", str(exc.detail))

    @app.exception_handler(RequestValidationError)
    async def handle_request_validation_error(
        _: Request, exc: RequestValidationError
    ) -> JSONResponse:
        return _error_response(422, "validation_error", "Request validation failed.")

    @app.exception_handler(Exception)
    async def handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("Unhandled error on %s %s", request.method, request.url.path)
        return _error_response(500, "internal_error", "Internal server error.")
