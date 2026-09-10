"""``configure_logging`` wires ``app.*`` logs to a stdout handler.

Without this the application's own loggers inherit a handler-less root at
WARNING and every ``logger.info`` (scan submitted / claimed / completed,
durations, finding counts, Gemini success / failure) is dropped.
"""

from __future__ import annotations

import importlib
import io
import logging
import sys


def _fresh_module():
    import app.logging_config as mod

    return importlib.reload(mod)


def test_configure_logging_attaches_one_stdout_handler_at_level() -> None:
    mod = _fresh_module()
    mod.configure_logging("INFO")

    app_logger = logging.getLogger("app")
    assert app_logger.level == logging.INFO
    assert len(app_logger.handlers) == 1
    handler = app_logger.handlers[0]
    assert isinstance(handler, logging.StreamHandler)
    assert handler.stream is sys.stdout


def test_configure_logging_is_idempotent() -> None:
    mod = _fresh_module()
    mod.configure_logging("INFO")
    first = list(logging.getLogger("app").handlers)
    mod.configure_logging("INFO")
    assert logging.getLogger("app").handlers == first


def test_app_info_records_are_emitted_by_the_handler() -> None:
    mod = _fresh_module()
    mod.configure_logging("INFO")

    # Point the (single) handler at a buffer we can read back.
    buffer = io.StringIO()
    logging.getLogger("app").handlers[0].stream = buffer

    logging.getLogger("app.worker").info("scan 123 completed: 4 findings in 1.20s")
    logging.getLogger("app.services.scans").debug("noisy detail")

    contents = buffer.getvalue()
    assert "scan 123 completed: 4 findings in 1.20s" in contents
    assert "noisy detail" not in contents


def test_level_can_be_raised_to_warning() -> None:
    mod = _fresh_module()
    mod.configure_logging("WARNING")

    buffer = io.StringIO()
    logging.getLogger("app").handlers[0].stream = buffer

    logging.getLogger("app.services.scans").info("queued scan x")
    logging.getLogger("app.services.scans").warning("rejecting scan: at capacity")

    contents = buffer.getvalue()
    assert "queued scan x" not in contents
    assert "rejecting scan: at capacity" in contents
