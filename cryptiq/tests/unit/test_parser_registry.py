"""The parser registry."""

from app.engine.parser import PythonParser, get_parser, register, supported_languages
from app.engine.parser.registry import _PARSERS


def test_python_is_registered() -> None:
    parser = get_parser("python")

    assert isinstance(parser, PythonParser)
    assert parser.language == "python"
    assert parser.version == "python-ast-1"


def test_an_unknown_language_has_no_parser() -> None:
    assert get_parser("rust") is None
    assert get_parser("") is None


def test_supported_languages_are_listed_in_a_stable_order() -> None:
    assert supported_languages() == tuple(sorted(supported_languages()))
    assert "python" in supported_languages()


def test_a_language_can_be_registered_and_replaced() -> None:
    original = dict(_PARSERS)
    try:
        parser = PythonParser()
        register("python-experimental", parser)

        assert get_parser("python-experimental") is parser
        assert "python-experimental" in supported_languages()
    finally:
        _PARSERS.clear()
        _PARSERS.update(original)
