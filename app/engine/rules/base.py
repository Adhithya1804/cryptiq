from __future__ import annotations

import ast
from typing import Protocol, runtime_checkable

from app.engine.models import AnalysisContext, RuleMatch


@runtime_checkable
class CryptoRule(Protocol):
    """
    Protocol defining the pure static analysis rule interface.
    Rules inspect AST nodes in context and return a RuleMatch if a cryptographic primitive is detected.
    """
    rule_id: str

    def evaluate(
        self,
        node: ast.AST,
        context: AnalysisContext,
    ) -> RuleMatch | None:
        """
        Pure evaluation of an individual AST node within an analysis context.
        Must never execute or import repository code.
        """
        ...
