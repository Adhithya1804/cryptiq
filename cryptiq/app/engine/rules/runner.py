"""Running the registered rules over parsed files.

Only call nodes are offered to the rules, and each call node is offered once,
so a construct that appears in the AST as several nested nodes still yields at
most one observation per rule.
"""

import logging
from collections.abc import Iterable, Sequence

from app.engine.parser import ParsedFile
from app.engine.rules.base import AnalysisContext, CryptoRule, RuleMatch
from app.engine.rules.registry import all_rules

logger = logging.getLogger(__name__)


def evaluate_file(
    file: ParsedFile, rules: Sequence[CryptoRule] | None = None
) -> list[RuleMatch]:
    """Return every observation in one parsed file, in a stable order."""
    if not file.parsed:
        return []

    active = tuple(rules) if rules is not None else all_rules()
    context = AnalysisContext(file=file)
    matches = [
        match
        for call in file.calls
        for rule in active
        if (match := rule.evaluate(call.node, context)) is not None
    ]
    return sorted(matches, key=lambda match: match.sort_key)


def evaluate_files(
    files: Iterable[ParsedFile], rules: Sequence[CryptoRule] | None = None
) -> list[RuleMatch]:
    """Return every observation across many files, in a stable order."""
    matches = [match for file in files for match in evaluate_file(file, rules)]
    matches.sort(key=lambda match: match.sort_key)
    logger.info("rules produced %d observations", len(matches))
    return matches
