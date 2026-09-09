"""Compatibility layer for Phases 1-8 integration."""

from cryptiq.compat.interfaces import (
    AnalysisEngine,
    AnalysisResult,
    RuleMatch,
    SourceProvider,
    SourceSnapshot,
)

__all__ = [
    "SourceSnapshot",
    "RuleMatch",
    "AnalysisResult",
    "SourceProvider",
    "AnalysisEngine",
]
