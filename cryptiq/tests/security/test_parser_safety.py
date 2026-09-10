"""The parser is static, and one hostile file cannot end a scan."""

import ast
import sys
from pathlib import Path

import pytest

from app.engine.parser import ParseErrorType, PythonParser, parse_sources

PARSER_PACKAGE = Path(__file__).resolve().parents[2] / "app" / "engine" / "parser"
PARSER_SOURCES = sorted(path.name for path in PARSER_PACKAGE.glob("*.py"))


def test_a_syntax_error_becomes_a_structured_failure() -> None:
    parsed = PythonParser().parse("def broken(:\n", "broken.py")

    assert not parsed.parsed
    assert parsed.tree is None
    assert parsed.error.path == "broken.py"
    assert parsed.error.error_type is ParseErrorType.SYNTAX_ERROR
    assert parsed.error.line == 1


def test_a_syntax_error_message_carries_no_traceback_or_path() -> None:
    parsed = PythonParser().parse("class ??:\n", "/private/repo/secret.py")

    assert "Traceback" not in parsed.error.message
    assert "/private/repo" not in parsed.error.message


def test_a_null_byte_in_source_fails_safely() -> None:
    parsed = PythonParser().parse("x = 1\x00\n", "nul.py")

    assert not parsed.parsed
    assert parsed.error.error_type in {
        ParseErrorType.INVALID_SOURCE,
        ParseErrorType.SYNTAX_ERROR,
    }


def test_one_broken_file_does_not_stop_the_others() -> None:
    results = parse_sources(
        [
            ("b_broken.py", "def broken(:\n"),
            ("a_ok.py", "value = compute()\n"),
            ("c_ok.py", "class Signer:\n    pass\n"),
        ]
    )

    assert [file.path for file in results] == ["a_ok.py", "b_broken.py", "c_ok.py"]
    assert [file.parsed for file in results] == [True, False, True]
    assert results[0].calls[0].function == "compute"


def test_deeply_nested_but_valid_source_is_represented() -> None:
    source = "value = " + "[" * 40 + "]" * 40 + "\n"

    parsed = PythonParser().parse(source, "nested.py")

    assert parsed.parsed
    assert parsed.assignments[0].targets == ("value",)


def test_pathological_nesting_fails_safely_rather_than_crashing() -> None:
    # Beyond CPython's own compiler limits. Whatever it raises, the file must
    # come back as a parse error and the process must keep running.
    source = "value = " + "[" * 5000 + "]" * 5000 + "\n"

    parsed = PythonParser().parse(source, "bomb.py")

    if parsed.parsed:
        pytest.skip("this interpreter represents the nesting without complaint")
    assert parsed.error.error_type in {
        ParseErrorType.SYNTAX_ERROR,
        ParseErrorType.SOURCE_TOO_COMPLEX,
    }


def test_a_very_deep_expression_does_not_overflow_the_traversal() -> None:
    # The walk and the chain helper are both iterative, so an AST thousands of
    # levels deep must be described without exhausting the interpreter stack.
    depth = 5000
    source = "value = " + ".".join(["root"] + ["attribute"] * depth) + "\n"

    parsed = PythonParser().parse(source, "deep.py")

    assert parsed.parsed
    assert parsed.assignments[0].targets == ("value",)
    assert len(parsed.attributes[-1].chain) == depth + 1


def test_deeply_nested_blocks_are_traversed() -> None:
    # CPython refuses more than 100 levels of indentation, so this stays just
    # under its own limit and checks the traversal, not the compiler.
    depth = 90
    lines = [f"{'    ' * index}if value_{index}:\n" for index in range(depth)]
    lines.append(f"{'    ' * depth}sign(value)\n")

    parsed = PythonParser().parse("".join(lines), "deep.py")

    assert parsed.parsed
    assert parsed.calls[0].function == "sign"


def test_the_recursion_limit_is_left_alone() -> None:
    before = sys.getrecursionlimit()
    PythonParser().parse("value = compute()\n", "a.py")

    assert sys.getrecursionlimit() == before


@pytest.mark.parametrize("name", PARSER_SOURCES)
def test_the_parser_never_executes_source(name: str) -> None:
    """No dynamic execution primitive appears anywhere in the parser."""
    path = PARSER_PACKAGE / name
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=name)
    forbidden = {"exec", "eval", "compile", "__import__"}

    called = {
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    imported = {
        alias.name.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    } | {
        node.module.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module
    }

    assert not (called & forbidden)
    assert "importlib" not in imported
    assert "subprocess" not in imported
