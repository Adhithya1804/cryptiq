"""Deterministic cryptographic analysis engine.

Pipeline stages, in order: ingestion, discovery, parser, rules, evidence,
roles, pqc, impact, priority, fingerprints. Each stage is a separate
subpackage and consumes only the output of the stage before it. ``pipeline``
runs them over one extracted snapshot.

The stages divide into three kinds, and the division is part of the contract:

* **observed** -- rules and evidence. A reviewer can check these against the
  file. The algorithm, the API, the location and the source excerpt.
* **inferred** -- roles. What the engine concludes the construct is for.
* **derived** -- pqc, impact and priority. Consequences of the inference.

Nothing after the rule stage changes an observed fact.
"""

from app.engine.engine import engine_versions
from app.engine.models import EngineVersions
from app.engine.pipeline import AnalysisResult, AnalyzedFinding, analyze_snapshot

__all__ = [
    "AnalysisResult",
    "AnalyzedFinding",
    "EngineVersions",
    "analyze_snapshot",
    "engine_versions",
]
