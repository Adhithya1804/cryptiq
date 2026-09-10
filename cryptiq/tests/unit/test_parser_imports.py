"""Import extraction and the alias index."""

from app.engine.parser import PythonParser

RSA_MODULE = "cryptography.hazmat.primitives.asymmetric.rsa"


def parse(source: str, path: str = "src/signing.py"):
    return PythonParser().parse(source, path)


def test_plain_import_binds_the_top_level_package() -> None:
    parsed = parse("import cryptography\n")

    entry = parsed.imports[0]
    assert entry.local_name == "cryptography"
    assert entry.qualified_name == "cryptography"
    assert entry.module == "cryptography"
    assert entry.is_from_import is False
    assert entry.alias is None
    assert parsed.resolve("cryptography") == "cryptography"


def test_dotted_import_records_the_full_module_but_binds_the_root() -> None:
    parsed = parse(f"import {RSA_MODULE}\n")

    entry = parsed.imports[0]
    assert entry.local_name == "cryptography"
    assert entry.qualified_name == "cryptography"
    assert entry.module == RSA_MODULE


def test_aliased_import_binds_the_alias_to_the_full_path() -> None:
    parsed = parse("import cryptography as c\n")

    entry = parsed.imports[0]
    assert entry.local_name == "c"
    assert entry.qualified_name == "cryptography"
    assert entry.alias == "c"
    assert parsed.resolve("c") == "cryptography"


def test_aliased_dotted_import_resolves_to_the_full_module() -> None:
    parsed = parse(f"import {RSA_MODULE} as rsa_module\n")

    assert parsed.resolve("rsa_module") == RSA_MODULE


def test_from_import_resolves_the_member() -> None:
    parsed = parse(
        "from cryptography.hazmat.primitives.asymmetric import rsa\n"
    )

    entry = parsed.imports[0]
    assert entry.local_name == "rsa"
    assert entry.qualified_name == RSA_MODULE
    assert entry.imported_name == "rsa"
    assert entry.is_from_import is True
    assert parsed.resolve("rsa") == RSA_MODULE


def test_aliased_from_import_resolves_the_member() -> None:
    parsed = parse(f"from {RSA_MODULE} import RSAPrivateKey as Key\n")

    assert parsed.resolve("Key") == f"{RSA_MODULE}.RSAPrivateKey"
    assert parsed.imports[0].alias == "Key"


def test_several_names_in_one_from_import_are_all_recorded() -> None:
    parsed = parse(f"from {RSA_MODULE} import RSAPrivateKey, RSAPublicKey\n")

    assert parsed.resolve("RSAPrivateKey") == f"{RSA_MODULE}.RSAPrivateKey"
    assert parsed.resolve("RSAPublicKey") == f"{RSA_MODULE}.RSAPublicKey"


def test_a_relative_import_keeps_its_leading_dots() -> None:
    parsed = parse("from ..keys import loader\n")

    entry = parsed.imports[0]
    assert entry.level == 2
    assert entry.qualified_name == "..keys.loader"


def test_a_bare_relative_import_is_recorded() -> None:
    parsed = parse("from . import helpers\n")

    assert parsed.imports[0].qualified_name == ".helpers"
    assert parsed.imports[0].level == 1


def test_an_unimported_name_resolves_to_nothing() -> None:
    parsed = parse("import cryptography\n")

    assert parsed.resolve("rsa") is None


def test_imports_become_symbols_too() -> None:
    parsed = parse(f"from {RSA_MODULE} import rsa\n")

    assert [symbol.name for symbol in parsed.symbols] == ["rsa"]
    assert parsed.symbols[0].kind.value == "IMPORT"


def test_import_locations_are_exact() -> None:
    parsed = parse("x = 1\nimport cryptography\n")

    location = parsed.imports[0].location
    assert location.start_line == 2
    assert location.end_line == 2
    assert location.start_column == 0
