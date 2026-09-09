from __future__ import annotations

import ast
from collections import deque
from typing import Sequence

from app.engine.models import AnalysisContext, RuleMatch
from app.engine.rules.aes import AESRule
from app.engine.rules.base import CryptoRule
from app.engine.rules.ecdh import ECDHRule
from app.engine.rules.ecdsa import ECDSARule
from app.engine.rules.ed25519 import Ed25519Rule
from app.engine.rules.hashes import HashRule
from app.engine.rules.rsa import RSARule
from app.engine.rules.x25519 import X25519Rule

DEFAULT_MAX_AST_NODES = 100_000


class RuleRegistry:
    """
    Central registry managing active Cryptiq static analysis rules.
    Provides deterministic node and tree evaluation with strict node recursion limits.
    """

    def __init__(self, rules: Sequence[CryptoRule] | None = None) -> None:
        self._rules: dict[str, CryptoRule] = {}
        if rules:
            for rule in rules:
                self.register(rule)

    def register(self, rule: CryptoRule) -> None:
        """
        Register a new CryptoRule instance.
        """
        self._rules[rule.rule_id] = rule

    def unregister(self, rule_id: str) -> CryptoRule | None:
        """
        Remove a rule by ID.
        """
        return self._rules.pop(rule_id, None)

    def get(self, rule_id: str) -> CryptoRule | None:
        """
        Get a registered rule by its rule_id.
        """
        return self._rules.get(rule_id)

    def list_rules(self) -> list[CryptoRule]:
        """
        List all registered rules in insertion order.
        """
        return list(self._rules.values())

    def evaluate_node(
        self,
        node: ast.AST,
        context: AnalysisContext,
    ) -> list[RuleMatch]:
        """
        Evaluate a single AST node against all registered rules.
        """
        matches: list[RuleMatch] = []
        for rule in self._rules.values():
            match = rule.evaluate(node, context)
            if match is not None:
                matches.append(match)
        return matches

    def evaluate_tree(
        self,
        tree: ast.AST,
        context: AnalysisContext,
        max_nodes: int = DEFAULT_MAX_AST_NODES,
    ) -> list[RuleMatch]:
        """
        Iteratively traverse an AST tree using a bounded queue to prevent stack overflow
        and ensure deep AST recursion limits are strictly respected.
        """
        # Ensure context.parent_map contains mappings for this specific tree
        if context is not None:
            for parent in ast.walk(tree):
                for child in ast.iter_child_nodes(parent):
                    context.parent_map[id(child)] = parent

        matches: list[RuleMatch] = []
        queue: deque[ast.AST] = deque([tree])
        nodes_visited = 0

        while queue:
            node = queue.popleft()
            nodes_visited += 1
            if nodes_visited > max_nodes:
                # Bounded execution safeguard against malicious deep AST attacks
                break

            for rule in self._rules.values():
                match = rule.evaluate(node, context)
                if match is not None:
                    matches.append(match)

            for child in ast.iter_child_nodes(node):
                queue.append(child)

        return matches

    @classmethod
    def default_registry(cls) -> RuleRegistry:
        """
        Create a RuleRegistry pre-populated with all standard Phase 6 crypto rules.
        """
        return cls(
            rules=[
                RSARule(),
                ECDSARule(),
                Ed25519Rule(),
                ECDHRule(),
                X25519Rule(),
                AESRule(),
                HashRule(),
            ]
        )
