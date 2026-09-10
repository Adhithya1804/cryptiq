"""The parser registry.

A small, explicit table of the languages the engine can represent. Parsers are
registered by this module at import time; nothing is ever discovered or
imported from repository content.
"""

from app.engine.parser.base import SourceParser
from app.engine.parser.python import LANGUAGE as PYTHON_LANGUAGE
from app.engine.parser.python import PythonParser

_PARSERS: dict[str, SourceParser] = {}


def register(language: str, parser: SourceParser) -> None:
    """Register a parser for a language, replacing any previous one."""
    _PARSERS[language] = parser


def get_parser(language: str) -> SourceParser | None:
    """Return the parser for a language, or None when it is not supported."""
    return _PARSERS.get(language)


def supported_languages() -> tuple[str, ...]:
    """Return the registered languages, in a stable order."""
    return tuple(sorted(_PARSERS))


register(PYTHON_LANGUAGE, PythonParser())
