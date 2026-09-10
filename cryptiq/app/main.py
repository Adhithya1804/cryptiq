"""FastAPI application factory and entry point."""

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.api.v1.health import router as health_router
from app.api.v1.router import api_router
from app.config import get_settings
from app.errors import register_error_handlers
from app.logging_config import configure_logging
from app.middleware import BodySizeLimitMiddleware
from app.worker import worker_loop

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Run the in-process scan worker for the lifetime of the application."""
    settings = get_settings()
    logger.info(
        "cryptiq %s starting (env=%s, worker=%s, docs=%s)",
        __version__,
        settings.environment,
        settings.run_worker,
        settings.expose_api_docs,
    )
    stop = asyncio.Event()
    task: asyncio.Task[None] | None = None
    if settings.run_worker:
        task = asyncio.create_task(worker_loop(stop))
    try:
        yield
    finally:
        if task is not None:
            stop.set()
            try:
                await asyncio.wait_for(task, timeout=10)
            except TimeoutError:  # pragma: no cover - defensive
                task.cancel()


def create_app() -> FastAPI:
    """Build the FastAPI application."""
    settings = get_settings()
    configure_logging()
    # The interactive docs and raw schema are useful locally but only widen the
    # surface of an unauthenticated demo endpoint; the AWS profile turns them
    # off (EXPOSE_API_DOCS=false).
    docs_kwargs: dict[str, str | None] = {}
    if not settings.expose_api_docs:
        docs_kwargs = {"docs_url": None, "redoc_url": None, "openapi_url": None}
    app = FastAPI(
        title="Cryptiq",
        version=__version__,
        description="Deterministic cryptographic static-analysis backend.",
        lifespan=lifespan,
        **docs_kwargs,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "PATCH", "OPTIONS"],
        allow_headers=["Content-Type", "Accept"],
    )
    app.add_middleware(
        BodySizeLimitMiddleware, max_bytes=settings.max_request_body_bytes
    )
    register_error_handlers(app)
    app.include_router(api_router, prefix="/api/v1")
    # Unprefixed alias so process supervisors and load balancers can probe a
    # stable path that does not move with the API version.
    app.include_router(health_router, include_in_schema=False)
    return app


app = create_app()


def run() -> None:
    """Run the development server."""
    import uvicorn

    uvicorn.run("app.main:app", host="127.0.0.1", port=8000, reload=True)
