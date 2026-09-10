"""Symbols, calls, attributes, names, assignments and annotations."""

import ast

import pytest

from app.engine.parser import PythonParser, SymbolKind, attribute_chain, module_path_for


def parse(source: str, path: str = "src/signing.py"):
    return PythonParser().parse(source, path)


def qualified_names(parsed, kind: SymbolKind) -> list[str]:
    return [symbol.qualified_name for symbol in parsed.symbols_of(kind)]


def test_a_function_is_recorded_with_its_span() -> None:
    parsed = parse("def sign(payload):\n    return payload\n")

    symbol = parsed.symbols[0]
    assert symbol.kind is SymbolKind.FUNCTION
    assert symbol.name == "sign"
    assert symbol.qualified_name == "sign"
    assert symbol.path == "src/signing.py"
    assert symbol.parent is None
    assert symbol.location.start_line == 1
    assert symbol.location.end_line == 2


def test_an_async_function_is_distinguished() -> None:
    parsed = parse("async def sign(payload):\n    return payload\n")

    assert parsed.symbols[0].kind is SymbolKind.ASYNC_FUNCTION


def test_a_class_and_its_methods_are_qualified() -> None:
    parsed = parse(
        "class Signer:\n"
        "    def sign(self, payload):\n"
        "        return payload\n"
        "\n"
        "    async def sign_async(self, payload):\n"
        "        return payload\n"
    )

    assert qualified_names(parsed, SymbolKind.CLASS) == ["Signer"]
    assert qualified_names(parsed, SymbolKind.FUNCTION) == ["Signer.sign"]
    assert qualified_names(parsed, SymbolKind.ASYNC_FUNCTION) == ["Signer.sign_async"]
    assert parsed.symbols[1].parent == "Signer"


def test_a_nested_function_is_qualified_by_its_parent() -> None:
    parsed = parse(
        "def outer():\n"
        "    def inner():\n"
        "        return 1\n"
        "    return inner\n"
    )

    assert qualified_names(parsed, SymbolKind.FUNCTION) == ["outer", "outer.inner"]
    assert parsed.symbols[1].parent == "outer"


def test_a_nested_class_is_qualified() -> None:
    parsed = parse("class Outer:\n    class Inner:\n        pass\n")

    assert qualified_names(parsed, SymbolKind.CLASS) == ["Outer", "Outer.Inner"]


def test_a_call_records_its_enclosing_definitions() -> None:
    parsed = parse(
        "class Signer:\n"
        "    def sign(self, key, payload):\n"
        "        return key.sign(payload)\n"
    )

    call = parsed.calls[0]
    assert call.function == "key.sign"
    assert call.chain == ("key", "sign")
    assert call.attribute == "sign"
    assert call.root == "key"
    assert call.enclosing_function == "Signer.sign"
    assert call.enclosing_class == "Signer"
    assert call.path == "src/signing.py"


def test_a_module_level_call_has_no_enclosing_definitions() -> None:
    parsed = parse("value = compute()\n")

    assert parsed.calls[0].enclosing_function is None
    assert parsed.calls[0].enclosing_class is None


def test_nested_calls_are_all_recorded_in_source_order() -> None:
    parsed = parse("outer(middle(inner()))\n")

    assert [call.function for call in parsed.calls] == ["outer", "middle", "inner"]


def test_call_arguments_are_described_but_not_evaluated() -> None:
    parsed = parse(
        "key = rsa.generate_private_key(\n"
        "    public_exponent=65537,\n"
        "    key_size=2048,\n"
        ")\n"
    )

    call = parsed.calls[0]
    assert call.function == "rsa.generate_private_key"
    assert call.positional_arguments == ()
    assert {name: argument.constant for name, argument in call.keyword_arguments.items()} == {
        "public_exponent": 65537,
        "key_size": 2048,
    }


def test_positional_arguments_keep_their_expressions() -> None:
    parsed = parse("key.sign(payload, padding.PSS(), hashes.SHA256())\n")

    outer = parsed.calls[0]
    expressions = [argument.expression for argument in outer.positional_arguments]
    assert expressions == ["payload", None, None]
    assert outer.positional_arguments[1].node.func.attr == "PSS"


def test_a_callee_that_is_itself_a_call_has_no_chain() -> None:
    parsed = parse("factory().sign(payload)\n")

    outer = next(call for call in parsed.calls if call.attribute == "sign")
    assert outer.function is None
    assert outer.chain is None
    assert outer.attribute == "sign"


def test_a_long_literal_is_not_copied_into_the_representation() -> None:
    parsed = parse(f"log('{'a' * 300}')\n")

    assert parsed.calls[0].positional_arguments[0].constant is None


def test_every_attribute_node_in_a_chain_is_recorded() -> None:
    parsed = parse("value = foo.bar.baz\n")

    # ``foo.bar.baz`` is an Attribute wrapping another Attribute, so both are
    # described; a rule can match on the full chain or on any prefix of it.
    assert [attribute.expression for attribute in parsed.attributes] == [
        "foo.bar",
        "foo.bar.baz",
    ]
    outermost = parsed.attributes[-1]
    assert outermost.chain == ("foo", "bar", "baz")
    assert outermost.attribute == "baz"
    assert outermost.root == "foo"


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("rsa.RSAPrivateKey", ("rsa", "RSAPrivateKey")),
        ("private_key.sign", ("private_key", "sign")),
        ("foo.bar.baz", ("foo", "bar", "baz")),
        ("name", ("name",)),
        ("some_call().sign", None),
        ("items[0].sign", None),
        ("'literal'.upper", None),
    ],
)
def test_attribute_chain_helper(source: str, expected: tuple[str, ...] | None) -> None:
    node = ast.parse(source).body[0].value

    assert attribute_chain(node) == expected


def test_names_record_their_context() -> None:
    parsed = parse("value = other\ndel value\n")

    contexts = {(name.name, name.context.value) for name in parsed.names}
    assert ("value", "STORE") in contexts
    assert ("other", "LOAD") in contexts
    assert ("value", "DELETE") in contexts


def test_assignments_record_targets_and_value_shape() -> None:
    parsed = parse(
        "private_key = load_private_key()\n"
        "key = rsa.generate_private_key()\n"
        "handler = obj.sign\n"
    )

    by_target = {assignment.targets[0]: assignment for assignment in parsed.assignments}
    assert by_target["private_key"].value_call == "load_private_key"
    assert by_target["key"].value_call == "rsa.generate_private_key"
    assert by_target["handler"].value_expression == "obj.sign"
    assert by_target["handler"].value_call is None


def test_tuple_targets_are_unpacked() -> None:
    parsed = parse("public, private = generate()\n")

    assert parsed.assignments[0].targets == ("public", "private")


def test_a_walrus_is_recorded_as_an_assignment() -> None:
    parsed = parse("if (key := load()):\n    pass\n")

    assert parsed.assignments[0].targets == ("key",)
    assert parsed.assignments[0].value_call == "load"


def test_annotated_assignments_record_the_annotation() -> None:
    parsed = parse("key: rsa.RSAPrivateKey = load()\n")

    annotation = parsed.annotations[0]
    assert annotation.target == "key"
    assert annotation.annotation_expression == "rsa.RSAPrivateKey"
    assert annotation.annotation_chain == ("rsa", "RSAPrivateKey")
    assert parsed.assignments[0].is_annotated is True


def test_a_bare_annotation_is_recorded() -> None:
    parsed = parse("x: RSAPrivateKey\n")

    assert parsed.annotations[0].annotation_expression == "RSAPrivateKey"
    assert parsed.assignments[0].value_expression is None


def test_parameter_and_return_annotations_are_recorded() -> None:
    parsed = parse("def sign(key: rsa.RSAPrivateKey) -> bytes:\n    return b''\n")

    expressions = {annotation.annotation_expression for annotation in parsed.annotations}
    assert expressions == {"rsa.RSAPrivateKey", "bytes"}
    assert all(annotation.enclosing_function == "sign" for annotation in parsed.annotations)


def test_module_level_bindings_become_symbols_but_locals_do_not() -> None:
    parsed = parse(
        "BACKEND = default_backend()\n"
        "class Signer:\n"
        "    algorithm = 'rsa'\n"
        "\n"
        "def sign():\n"
        "    local = 1\n"
        "    return local\n"
    )

    assert qualified_names(parsed, SymbolKind.VARIABLE) == ["BACKEND", "Signer.algorithm"]


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("src/signing.py", "src.signing"),
        ("signing.py", "signing"),
        ("src/pkg/__init__.py", "src.pkg"),
        ("src/not-a-module.py", None),
        ("src/module.txt", None),
        ("__init__.py", None),
    ],
)
def test_module_path_derivation(path: str, expected: str | None) -> None:
    assert module_path_for(path) == expected
