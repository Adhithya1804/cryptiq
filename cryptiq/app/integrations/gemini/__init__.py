"""Gemini source of natural-language explanations.

The engine never imports this package. An explanation restates deterministic
findings for a reader; it never establishes a fact and never reaches the
browser -- the API key stays in the process. This package is the single
integration point for the Gemini SDK.
"""

from app.integrations.gemini.client import GeminiClient, GeminiError

__all__ = ["GeminiClient", "GeminiError"]
