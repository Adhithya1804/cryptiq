"""The Cryptiq standalone command-line interface.

One CLI, two execution modes over **one** analysis engine:

* **local** -- ``cryptiq scan <path>`` runs ``app.engine.pipeline`` in-process
  over a local directory or Git commit. No FastAPI, database, Docker, Redis,
  Celery, Kafka, cloud service or Gemini is involved, and the source never
  leaves the machine.
* **remote** -- ``cryptiq scan <url> --remote`` (and the persistent-store
  commands ``finding`` / ``review-queue`` / ``review-update`` / ``findings`` /
  ``scan-status`` / ``demo``) is a thin HTTP client of the running FastAPI
  backend, which runs the same engine behind ``ScanService``.

The deterministic engine stays the single source of truth in both modes: the
CLI adds no parsing, rules, role inference, PQC mapping, impact, priority or
fingerprint logic of its own.

Entry points:

* ``cryptiq`` console script -> :func:`app.cli.main.main`
* ``python -m app.cli`` -> the same
"""

from app.cli.main import main

__all__ = ["main"]
