"""Minimal application logging setup.

FastAPI/uvicorn configure only their own loggers; the application's ``app.*``
loggers inherit the root logger, which has no handler and sits at WARNING, so
every ``logger.info(...)`` in the worker and services is silently dropped. This
attaches one stdout handler to the ``app`` logger at the configured level so
Docker — and therefore CloudWatch — captures the operational events
(scan submitted / claimed / started / completed / failed, durations, finding
counts, Gemini success / failure). No framework, no config files.
"""

from __future__ import annotations

import logging
import sys

_CONFIGURED = False
_FORMAT = "%(asctime)s %(levelname)s %(name)s %(message)s"


def configure_logging(level: str | None = None) -> None:
    """Send ``app.*`` logs to stdout at ``level`` (default from settings).

    Idempotent: safe to call from the app factory on every import.
    """
    global _CONFIGURED
    if _CONFIGURED:
        return

    from app.config import get_settings

    resolved = (level or get_settings().log_level or "INFO").upper()
    numeric = getattr(logging, resolved, logging.INFO)

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter(_FORMAT))

    app_logger = logging.getLogger("app")
    app_logger.setLevel(numeric)
    # Own handler so the level holds regardless of what uvicorn does to root,
    # and don't double-emit if a root handler is later added.
    app_logger.handlers = [handler]
    app_logger.propagate = False

    # ``logging.config.fileConfig`` (Alembic runs it from alembic.ini) defaults
    # to disable_existing_loggers=True, which leaves the ``app`` logger and its
    # children disabled. Our explicit setup always re-enables the subtree.
    app_logger.disabled = False
    for name, logger in logging.root.manager.loggerDict.items():
        if name.startswith("app.") and isinstance(logger, logging.Logger):
            logger.disabled = False

    _CONFIGURED = True
