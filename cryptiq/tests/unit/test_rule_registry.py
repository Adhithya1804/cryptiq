"""The rule registry."""

import pytest

from app.engine.rules import (
    AesRule,
    EcdhRule,
    EcdsaRule,
    Ed25519Rule,
    HashRule,
    RsaRule,
    X25519Rule,
    all_rules,
    get_rule,
    register,
    registered_rule_ids,
)
from app.engine.rules.registry import _RULES

EXPECTED_RULE_IDS = (
    "PY-CRYPTO-AES",
    "PY-CRYPTO-ECDH",
    "PY-CRYPTO-ECDSA",
    "PY-CRYPTO-ED25519",
    "PY-CRYPTO-HASH",
    "PY-CRYPTO-RSA",
    "PY-CRYPTO-X25519",
)


def test_every_rule_of_this_phase_is_registered() -> None:
    assert registered_rule_ids() == EXPECTED_RULE_IDS


@pytest.mark.parametrize("rule_id", EXPECTED_RULE_IDS)
def test_each_rule_is_reachable_and_versioned(rule_id: str) -> None:
    rule = get_rule(rule_id)

    assert rule is not None
    assert rule.rule_id == rule_id
    assert rule.version == "0.3.0"


def test_the_rsa_rule_is_unchanged() -> None:
    assert isinstance(get_rule("PY-CRYPTO-RSA"), RsaRule)


@pytest.mark.parametrize(
    ("rule", "rule_id"),
    [
        (EcdsaRule, "PY-CRYPTO-ECDSA"),
        (Ed25519Rule, "PY-CRYPTO-ED25519"),
        (EcdhRule, "PY-CRYPTO-ECDH"),
        (X25519Rule, "PY-CRYPTO-X25519"),
    ],
)
def test_the_shared_rule_shapes_carry_their_own_identity(rule, rule_id: str) -> None:
    assert rule.rule_id == rule_id
    assert get_rule(rule_id) is rule


def test_the_standalone_rules_are_registered() -> None:
    assert isinstance(get_rule("PY-CRYPTO-AES"), AesRule)
    assert isinstance(get_rule("PY-CRYPTO-HASH"), HashRule)


def test_an_unknown_rule_is_absent() -> None:
    assert get_rule("PY-CRYPTO-DSA") is None


def test_rules_are_returned_in_a_stable_order() -> None:
    assert [rule.rule_id for rule in all_rules()] == list(EXPECTED_RULE_IDS)
    assert registered_rule_ids() == tuple(sorted(registered_rule_ids()))


def test_a_rule_can_be_registered_and_replaced() -> None:
    original = dict(_RULES)
    try:
        rule = RsaRule()
        rule.rule_id = "PY-CRYPTO-AAA"
        register(rule)

        assert all_rules()[0].rule_id == "PY-CRYPTO-AAA"
    finally:
        _RULES.clear()
        _RULES.update(original)
