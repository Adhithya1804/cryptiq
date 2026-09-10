"""The golden fixture: exactly what Phase 5 rules will read.

Nothing here names a cryptographic algorithm. The parser reports syntax; the
rules stage decides what it means.
"""

from app.engine.parser import PythonParser, SymbolKind

SOURCE = """from cryptography.hazmat.primitives.asymmetric import rsa


def sign_data(private_key, payload):
    signature = private_key.sign(
        payload,
        padding.PSS(
            mgf=padding.MGF1(hashes.SHA256()),
            salt_length=padding.PSS.MAX_LENGTH,
        ),
        hashes.SHA256(),
    )
    return signature
"""

RSA_MODULE = "cryptography.hazmat.primitives.asymmetric.rsa"


def parsed():
    return PythonParser().parse(SOURCE, "src/signing.py")


def test_the_file_parses_and_is_identified() -> None:
    file = parsed()

    assert file.parsed
    assert file.error is None
    assert file.path == "src/signing.py"
    assert file.language == "python"
    assert file.parser_version == "python-ast-1"
    assert file.module_path == "src.signing"


def test_the_imported_module_is_exposed_with_its_full_path() -> None:
    file = parsed()

    assert file.resolve("rsa") == RSA_MODULE
    assert file.imports[0].location.start_line == 1


def test_the_function_is_exposed_with_its_exact_span() -> None:
    file = parsed()

    function = next(file.symbols_of(SymbolKind.FUNCTION))
    assert function.name == "sign_data"
    assert function.qualified_name == "sign_data"
    assert function.location.start_line == 4
    assert function.location.end_line == 13
    assert function.location.start_column == 0


def test_the_method_call_is_exposed_with_its_multiline_span() -> None:
    file = parsed()

    call = next(call for call in file.calls if call.function == "private_key.sign")
    assert call.chain == ("private_key", "sign")
    assert call.attribute == "sign"
    assert call.root == "private_key"
    assert call.enclosing_function == "sign_data"
    assert call.enclosing_class is None
    assert call.location.start_line == 5
    assert call.location.end_line == 12
    assert call.location.start_column == 16
    assert call.location.end_column == 5


def test_the_nested_argument_calls_are_exposed() -> None:
    file = parsed()

    functions = [call.function for call in file.calls]
    assert functions == [
        "private_key.sign",
        "padding.PSS",
        "padding.MGF1",
        "hashes.SHA256",
        "hashes.SHA256",
    ]
    assert all(call.enclosing_function == "sign_data" for call in file.calls)


def test_the_call_arguments_stay_structural() -> None:
    file = parsed()

    call = next(call for call in file.calls if call.function == "private_key.sign")
    assert len(call.positional_arguments) == 3
    assert call.positional_arguments[0].expression == "payload"
    assert call.keyword_arguments == {}

    pss = next(call for call in file.calls if call.function == "padding.PSS")
    assert set(pss.keyword_arguments) == {"mgf", "salt_length"}
    assert pss.keyword_arguments["salt_length"].chain == (
        "padding",
        "PSS",
        "MAX_LENGTH",
    )


def test_the_assignment_is_exposed() -> None:
    file = parsed()

    assignment = file.assignments[0]
    assert assignment.targets == ("signature",)
    assert assignment.value_call == "private_key.sign"
    assert assignment.enclosing_function == "sign_data"
    assert assignment.location.start_line == 5


def test_the_representation_is_stable_across_runs() -> None:
    first = parsed()
    second = parsed()

    assert first.imports == second.imports
    assert first.symbols == second.symbols
    assert first.calls == second.calls
    assert first.assignments == second.assignments
    assert first.import_index == second.import_index
