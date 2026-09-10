"""The Cryptiq developer/demo command-line interface.

The CLI is a thin client over the running FastAPI backend. It never imports the
engine, the repositories or the database: every command is one or more calls to
the same HTTP endpoints the React frontend uses, so the deterministic engine
stays the single source of truth.

Entry points:

* ``cryptiq`` console script -> :func:`app.cli.main.main`
* ``python -m app.cli`` -> the same
"""

from app.cli.main import main

__all__ = ["main"]
