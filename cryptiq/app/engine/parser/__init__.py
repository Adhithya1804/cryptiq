"""Parser: turn source files into a syntactic representation for the rules.

The representation says what the syntax says and nothing more. Cryptographic
meaning is decided by the rules stage, which reads a ParsedFile.
"""

from app.engine.parser.base import (
    Annotation,
    Assignment,
    AttributeAccess,
    Call,
    CallArgument,
    ImportedName,
    NameContext,
    NameReference,
    NodeContext,
    ParsedFile,
    ParseError,
    ParseErrorType,
    SourceLocation,
    SourceParser,
    Symbol,
    SymbolKind,
    attribute_chain,
    dotted_name,
)
from app.engine.parser.batch import parse_all, parse_sources
from app.engine.parser.python import PythonParser, module_path_for
from app.engine.parser.registry import get_parser, register, supported_languages

__all__ = [
    "Annotation",
    "Assignment",
    "AttributeAccess",
    "Call",
    "CallArgument",
    "ImportedName",
    "NameContext",
    "NameReference",
    "NodeContext",
    "ParseError",
    "ParseErrorType",
    "ParsedFile",
    "PythonParser",
    "SourceLocation",
    "SourceParser",
    "Symbol",
    "SymbolKind",
    "attribute_chain",
    "dotted_name",
    "get_parser",
    "module_path_for",
    "parse_all",
    "parse_sources",
    "register",
    "supported_languages",
]
