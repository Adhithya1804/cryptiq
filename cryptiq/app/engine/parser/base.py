"""Provider-neutral parser interface and the representation it produces.

Nothing here interprets what the source means. A ParsedFile says only what the
syntax says: these names were imported, this expression was called, at these
exact locations. Cryptographic judgement belongs to the rules that read it.
"""

import ast
from collections.abc import Iterator, Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Protocol


class ParseErrorType(StrEnum):
    """Why a file could not be represented."""

    SYNTAX_ERROR = "SYNTAX_ERROR"
    SOURCE_TOO_COMPLEX = "SOURCE_TOO_COMPLEX"
    INVALID_SOURCE = "INVALID_SOURCE"
    READ_ERROR = "READ_ERROR"


class SymbolKind(StrEnum):
    """What kind of definition a symbol is."""

    MODULE = "MODULE"
    FUNCTION = "FUNCTION"
    ASYNC_FUNCTION = "ASYNC_FUNCTION"
    CLASS = "CLASS"
    VARIABLE = "VARIABLE"
    IMPORT = "IMPORT"


class NameContext(StrEnum):
    """How a name is used at one location."""

    LOAD = "LOAD"
    STORE = "STORE"
    DELETE = "DELETE"


@dataclass(frozen=True)
class SourceLocation:
    """An exact span in a source file.

    The four fields come straight from the AST node. Lines are 1-based and
    columns are 0-based, as CPython reports them; nothing is renumbered,
    because the evidence stage quotes source by these coordinates.
    """

    start_line: int
    end_line: int
    start_column: int
    end_column: int

    @classmethod
    def from_node(cls, node: ast.AST) -> "SourceLocation":
        """Read the span off an AST node, tolerating a missing end position."""
        start_line = getattr(node, "lineno", 0)
        start_column = getattr(node, "col_offset", 0)
        return cls(
            start_line=start_line,
            end_line=getattr(node, "end_lineno", None) or start_line,
            start_column=start_column,
            end_column=getattr(node, "end_col_offset", None) or start_column,
        )

    @property
    def sort_key(self) -> tuple[int, int, int, int]:
        """A total order over spans, used to keep every collection stable."""
        return (self.start_line, self.start_column, self.end_line, self.end_column)


@dataclass(frozen=True)
class ParseError:
    """A file that could not be parsed, and why."""

    path: str
    error_type: ParseErrorType
    message: str
    line: int | None = None
    column: int | None = None


@dataclass(frozen=True)
class NodeContext:
    """Where one AST node sits in the file.

    function and class_name are the qualified names of the nearest enclosing
    definitions, so a rule can ask "which function is this call in?" without
    walking anything itself.
    """

    node: ast.AST = field(compare=False, repr=False)
    parent: ast.AST | None = field(compare=False, repr=False)
    function: str | None
    class_name: str | None
    module: str | None


@dataclass(frozen=True)
class Symbol:
    """A definition or binding introduced by the module."""

    kind: SymbolKind
    name: str
    qualified_name: str
    path: str
    location: SourceLocation
    parent: str | None = None
    node: ast.AST | None = field(default=None, compare=False, repr=False)


@dataclass(frozen=True)
class ImportedName:
    """One name bound by an import statement.

    local_name is the binding the rest of the module sees. qualified_name is
    what it refers to. For a plain ``import a.b.c`` Python binds ``a``, so
    local_name is "a" and qualified_name is "a"; the full dotted path stays in
    module so a rule can still see what was imported.
    """

    local_name: str
    qualified_name: str
    module: str | None
    imported_name: str | None
    alias: str | None
    is_from_import: bool
    level: int
    location: SourceLocation
    node: ast.AST = field(compare=False, repr=False)


@dataclass(frozen=True)
class CallArgument:
    """One argument of a call, described but never evaluated."""

    keyword: str | None
    expression: str | None
    chain: tuple[str, ...] | None
    constant: object | None
    location: SourceLocation
    node: ast.AST = field(compare=False, repr=False)

    @property
    def is_keyword(self) -> bool:
        """True for ``name=value``; ``**kwargs`` also counts, with keyword None."""
        return self.keyword is not None


@dataclass(frozen=True)
class Call:
    """A call expression, exactly as written.

    function is the dotted text of the callable when it is a name or an
    attribute chain ("private_key.sign"), and None otherwise, for instance
    when the callable is itself a call. attribute holds the final attribute
    name whenever the callable is an attribute access, so a rule can still
    match ``factory().sign(...)``.
    """

    function: str | None
    chain: tuple[str, ...] | None
    attribute: str | None
    root: str | None
    path: str
    location: SourceLocation
    enclosing_function: str | None
    enclosing_class: str | None
    arguments: tuple[CallArgument, ...]
    node: ast.Call = field(compare=False, repr=False)

    @property
    def positional_arguments(self) -> tuple[CallArgument, ...]:
        return tuple(argument for argument in self.arguments if not argument.is_keyword)

    @property
    def keyword_arguments(self) -> Mapping[str, CallArgument]:
        return {
            argument.keyword: argument
            for argument in self.arguments
            if argument.keyword is not None
        }


@dataclass(frozen=True)
class AttributeAccess:
    """An attribute expression and its chain."""

    attribute: str
    chain: tuple[str, ...] | None
    expression: str | None
    root: str | None
    location: SourceLocation
    enclosing_function: str | None
    enclosing_class: str | None
    node: ast.Attribute = field(compare=False, repr=False)


@dataclass(frozen=True)
class NameReference:
    """One use of a bare name."""

    name: str
    context: NameContext
    location: SourceLocation
    enclosing_function: str | None
    enclosing_class: str | None
    node: ast.Name = field(compare=False, repr=False)


@dataclass(frozen=True)
class Assignment:
    """An assignment, with its targets and the shape of its value.

    No data flow is inferred. The value is described, not followed.
    value_expression and value_chain describe a plain name or attribute value
    ("x = obj.sign"); value_call names the callee when the value is a call
    ("key = rsa.generate_private_key(...)" gives "rsa.generate_private_key").
    """

    targets: tuple[str, ...]
    value_expression: str | None
    value_chain: tuple[str, ...] | None
    value_call: str | None
    is_annotated: bool
    location: SourceLocation
    enclosing_function: str | None
    enclosing_class: str | None
    node: ast.AST = field(compare=False, repr=False)


@dataclass(frozen=True)
class Annotation:
    """A type annotation attached to a name, parameter or attribute."""

    target: str | None
    annotation_expression: str | None
    annotation_chain: tuple[str, ...] | None
    location: SourceLocation
    enclosing_function: str | None
    enclosing_class: str | None
    node: ast.AST = field(compare=False, repr=False)


@dataclass(frozen=True)
class ParsedFile:
    """The full syntactic representation of one source file.

    Every collection is ordered by source location, so two runs over the same
    bytes produce identical results. The tree is kept as a live ``ast.AST``:
    it is an internal engine value and is never persisted.
    """

    path: str
    language: str
    parser_version: str
    module_path: str | None
    tree: ast.AST | None = field(compare=False, repr=False)
    imports: tuple[ImportedName, ...] = ()
    import_index: Mapping[str, str] = field(default_factory=dict)
    symbols: tuple[Symbol, ...] = ()
    calls: tuple[Call, ...] = ()
    attributes: tuple[AttributeAccess, ...] = ()
    names: tuple[NameReference, ...] = ()
    assignments: tuple[Assignment, ...] = ()
    annotations: tuple[Annotation, ...] = ()
    contexts: Mapping[int, NodeContext] = field(default_factory=dict, compare=False, repr=False)
    error: ParseError | None = None

    @property
    def parsed(self) -> bool:
        """True when the file produced a tree."""
        return self.error is None

    def context_for(self, node: ast.AST) -> NodeContext | None:
        """Return the recorded context for a node of this file's tree."""
        return self.contexts.get(id(node))

    def symbols_of(self, kind: SymbolKind) -> Iterator[Symbol]:
        """Yield this file's symbols of one kind, in source order."""
        return (symbol for symbol in self.symbols if symbol.kind is kind)

    def resolve(self, local_name: str) -> str | None:
        """Return what an imported binding refers to, or None if not imported."""
        return self.import_index.get(local_name)


class SourceParser(Protocol):
    """Turns decoded source text into a ParsedFile."""

    language: str
    version: str

    def parse(self, source: str, file_path: str) -> ParsedFile:
        """Represent one file. Never raises for bad source; returns an error instead."""
        ...


def attribute_chain(node: ast.AST) -> tuple[str, ...] | None:
    """Return the dotted chain of an attribute or name expression.

    ``rsa.RSAPrivateKey``  -> ("rsa", "RSAPrivateKey")
    ``private_key.sign``   -> ("private_key", "sign")
    ``foo.bar.baz``        -> ("foo", "bar", "baz")
    ``some_call().sign``   -> None

    A chain is returned only when every link is a plain attribute access
    rooted in a bare name. Anything else -- a call, a subscript, a literal --
    is not representable as a chain, and None says so rather than guessing.
    Callers that only need the final attribute should read it off the node.
    """
    parts: list[str] = []
    current = node
    while isinstance(current, ast.Attribute):
        parts.append(current.attr)
        current = current.value
    if not isinstance(current, ast.Name):
        return None
    parts.append(current.id)
    return tuple(reversed(parts))


def dotted_name(node: ast.AST) -> str | None:
    """Return the dotted text of a name or attribute expression, or None."""
    chain = attribute_chain(node)
    return ".".join(chain) if chain else None
