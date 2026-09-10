"""The Python parser.

Source text goes in and a syntactic description comes out. The module is
static from end to end: it calls ``ast.parse`` and walks the result. It never
compiles, executes, imports or otherwise runs a line of the repository, and it
never opens a file -- the caller supplies decoded text.
"""

import ast
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from pathlib import PurePosixPath

from app.engine.engine import engine_versions
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
    Symbol,
    SymbolKind,
    attribute_chain,
    dotted_name,
)

LANGUAGE = "python"
PACKAGE_INITIALIZER = "__init__.py"

# A literal longer than this is kept in the tree but not copied into the
# argument description; rules match on short values such as key sizes.
MAX_CONSTANT_LENGTH = 256

_NAME_CONTEXTS = {
    ast.Load: NameContext.LOAD,
    ast.Store: NameContext.STORE,
    ast.Del: NameContext.DELETE,
}

_FUNCTION_NODES = (ast.FunctionDef, ast.AsyncFunctionDef)


def _by_location(item: object) -> tuple[int, int, int, int]:
    """Sort key that puts any recorded item in source order."""
    return item.location.sort_key  # type: ignore[attr-defined]


@dataclass(frozen=True)
class _Scope:
    """The enclosing definitions at one point in the tree."""

    function: str | None = None
    class_name: str | None = None
    prefix: str = ""

    def qualify(self, name: str) -> str:
        return f"{self.prefix}.{name}" if self.prefix else name

    def entering_function(self, qualified_name: str) -> "_Scope":
        return _Scope(function=qualified_name, class_name=self.class_name, prefix=qualified_name)

    def entering_class(self, qualified_name: str) -> "_Scope":
        return _Scope(function=self.function, class_name=qualified_name, prefix=qualified_name)


def module_path_for(relative_path: str) -> str | None:
    """Derive a dotted module path from a relative file path.

    ``src/signing.py``          -> ``src.signing``
    ``src/pkg/__init__.py``     -> ``src.pkg``
    ``src/not-a-module.py``     -> ``None``

    Purely lexical. The package layout is never inspected and nothing is
    imported, so a path whose parts are not identifiers has no module path.
    """
    path = PurePosixPath(relative_path)
    if path.suffix != ".py":
        return None
    parts = list(path.parts[:-1])
    if path.name != PACKAGE_INITIALIZER:
        parts.append(path.stem)
    if not parts or not all(part.isidentifier() for part in parts):
        return None
    return ".".join(parts)


class PythonParser:
    """Represents Python source as names, calls, attributes and locations."""

    language = LANGUAGE

    @property
    def version(self) -> str:
        """The configured parser version, recorded on every ParsedFile."""
        return engine_versions().parser_version

    def parse(self, source: str, file_path: str) -> ParsedFile:
        """Represent one file, returning a parse error rather than raising."""
        try:
            tree = ast.parse(source, filename=file_path)
        except SyntaxError as exc:
            return self._failed(
                file_path,
                ParseErrorType.SYNTAX_ERROR,
                # exc.msg is CPython's own short description; the filename and
                # traceback are dropped so no internal path can leak.
                exc.msg or "Invalid Python syntax.",
                exc.lineno,
                exc.offset,
            )
        except ValueError as exc:
            return self._failed(
                file_path, ParseErrorType.INVALID_SOURCE, str(exc) or "Unreadable source."
            )
        except (RecursionError, MemoryError):
            # Deeply nested but syntactically valid source can exhaust the
            # compiler. One hostile file must not end the scan.
            return self._failed(
                file_path,
                ParseErrorType.SOURCE_TOO_COMPLEX,
                "Source is nested too deeply to represent.",
            )

        return _Builder(self, tree, file_path).build()

    def _failed(
        self,
        file_path: str,
        error_type: ParseErrorType,
        message: str,
        line: int | None = None,
        column: int | None = None,
    ) -> ParsedFile:
        return ParsedFile(
            path=file_path,
            language=self.language,
            parser_version=self.version,
            module_path=module_path_for(file_path),
            tree=None,
            error=ParseError(
                path=file_path,
                error_type=error_type,
                message=message,
                line=line,
                column=column,
            ),
        )


class _Builder:
    """Single-use walker that fills in one ParsedFile."""

    def __init__(self, parser: PythonParser, tree: ast.AST, file_path: str) -> None:
        self._parser = parser
        self._tree = tree
        self._path = file_path
        self._contexts: dict[int, NodeContext] = {}
        self._imports: list[ImportedName] = []
        self._symbols: list[Symbol] = []
        self._calls: list[Call] = []
        self._attributes: list[AttributeAccess] = []
        self._names: list[NameReference] = []
        self._assignments: list[Assignment] = []
        self._annotations: list[Annotation] = []
        self._module_path = module_path_for(file_path)

    def build(self) -> ParsedFile:
        """Walk the tree once and return the finished representation."""
        self._walk()
        imports = sorted(self._imports, key=_by_location)
        return ParsedFile(
            path=self._path,
            language=self._parser.language,
            parser_version=self._parser.version,
            module_path=self._module_path,
            tree=self._tree,
            imports=tuple(imports),
            import_index={entry.local_name: entry.qualified_name for entry in imports},
            symbols=tuple(sorted(self._symbols, key=_by_location)),
            calls=tuple(sorted(self._calls, key=_by_location)),
            attributes=tuple(sorted(self._attributes, key=_by_location)),
            names=tuple(sorted(self._names, key=_by_location)),
            assignments=tuple(sorted(self._assignments, key=_by_location)),
            annotations=tuple(sorted(self._annotations, key=_by_location)),
            contexts=self._contexts,
        )

    def _walk(self) -> None:
        """Traverse the tree iteratively.

        An explicit stack is used rather than recursion so that deeply nested
        source cannot overflow the interpreter while being described.
        """
        stack: list[tuple[ast.AST, ast.AST | None, _Scope]] = [(self._tree, None, _Scope())]
        while stack:
            node, parent, scope = stack.pop()
            self._record(node, parent, scope)
            child_scope = self._scope_within(node, scope)
            for child in reversed(list(ast.iter_child_nodes(node))):
                stack.append((child, node, child_scope))

    def _scope_within(self, node: ast.AST, scope: _Scope) -> _Scope:
        """Return the scope that applies to a node's children."""
        if isinstance(node, _FUNCTION_NODES):
            return scope.entering_function(scope.qualify(node.name))
        if isinstance(node, ast.ClassDef):
            return scope.entering_class(scope.qualify(node.name))
        return scope

    def _record(self, node: ast.AST, parent: ast.AST | None, scope: _Scope) -> None:
        self._contexts[id(node)] = NodeContext(
            node=node,
            parent=parent,
            function=scope.function,
            class_name=scope.class_name,
            module=self._module_path,
        )

        if isinstance(node, ast.Import):
            self._record_import(node)
        elif isinstance(node, ast.ImportFrom):
            self._record_import_from(node)
        elif isinstance(node, _FUNCTION_NODES):
            self._record_function(node, scope)
        elif isinstance(node, ast.ClassDef):
            self._record_class(node, scope)
        elif isinstance(node, ast.Call):
            self._calls.append(self._build_call(node, scope))
        elif isinstance(node, ast.Attribute):
            self._record_attribute(node, scope)
        elif isinstance(node, ast.Name):
            self._record_name(node, scope)
        elif isinstance(node, ast.Assign | ast.AugAssign | ast.NamedExpr):
            self._record_assignment(node, scope)
        elif isinstance(node, ast.AnnAssign):
            self._record_annotated_assignment(node, scope)
        elif isinstance(node, ast.arg) and node.annotation is not None:
            self._annotations.append(
                self._build_annotation(node.arg, node.annotation, node, scope)
            )

    def _record_import(self, node: ast.Import) -> None:
        location = SourceLocation.from_node(node)
        for alias in node.names:
            # ``import a.b.c`` binds ``a``; only an ``as`` clause binds the
            # full path. qualified_name records what the binding refers to.
            local_name = alias.asname or alias.name.split(".")[0]
            qualified = alias.name if alias.asname else local_name
            self._imports.append(
                ImportedName(
                    local_name=local_name,
                    qualified_name=qualified,
                    module=alias.name,
                    imported_name=None,
                    alias=alias.asname,
                    is_from_import=False,
                    level=0,
                    location=location,
                    node=node,
                )
            )
            self._symbols.append(
                Symbol(
                    kind=SymbolKind.IMPORT,
                    name=local_name,
                    qualified_name=local_name,
                    path=self._path,
                    location=location,
                    node=node,
                )
            )

    def _record_import_from(self, node: ast.ImportFrom) -> None:
        location = SourceLocation.from_node(node)
        # A relative import keeps its leading dots: resolving it would mean
        # assuming a package layout the parser is not allowed to inspect.
        prefix = "." * node.level + (node.module or "")
        for alias in node.names:
            local_name = alias.asname or alias.name
            qualified = _join_module(prefix, alias.name)
            self._imports.append(
                ImportedName(
                    local_name=local_name,
                    qualified_name=qualified,
                    module=node.module,
                    imported_name=alias.name,
                    alias=alias.asname,
                    is_from_import=True,
                    level=node.level,
                    location=location,
                    node=node,
                )
            )
            self._symbols.append(
                Symbol(
                    kind=SymbolKind.IMPORT,
                    name=local_name,
                    qualified_name=local_name,
                    path=self._path,
                    location=location,
                    node=node,
                )
            )

    def _record_function(self, node: ast.FunctionDef | ast.AsyncFunctionDef, scope: _Scope) -> None:
        kind = (
            SymbolKind.ASYNC_FUNCTION
            if isinstance(node, ast.AsyncFunctionDef)
            else SymbolKind.FUNCTION
        )
        self._symbols.append(
            Symbol(
                kind=kind,
                name=node.name,
                qualified_name=scope.qualify(node.name),
                path=self._path,
                location=SourceLocation.from_node(node),
                parent=scope.prefix or None,
                node=node,
            )
        )
        if node.returns is not None:
            inner = scope.entering_function(scope.qualify(node.name))
            self._annotations.append(
                self._build_annotation(node.name, node.returns, node, inner)
            )

    def _record_class(self, node: ast.ClassDef, scope: _Scope) -> None:
        self._symbols.append(
            Symbol(
                kind=SymbolKind.CLASS,
                name=node.name,
                qualified_name=scope.qualify(node.name),
                path=self._path,
                location=SourceLocation.from_node(node),
                parent=scope.prefix or None,
                node=node,
            )
        )

    def _build_call(self, node: ast.Call, scope: _Scope) -> Call:
        chain = attribute_chain(node.func)
        attribute = node.func.attr if isinstance(node.func, ast.Attribute) else None
        return Call(
            function=".".join(chain) if chain else None,
            chain=chain,
            attribute=attribute,
            root=chain[0] if chain else None,
            path=self._path,
            location=SourceLocation.from_node(node),
            enclosing_function=scope.function,
            enclosing_class=scope.class_name,
            arguments=tuple(self._build_arguments(node)),
            node=node,
        )

    def _build_arguments(self, node: ast.Call) -> Iterator[CallArgument]:
        for argument in node.args:
            yield self._build_argument(None, argument)
        for keyword in node.keywords:
            yield self._build_argument(keyword.arg, keyword.value)

    def _build_argument(self, keyword: str | None, value: ast.expr) -> CallArgument:
        chain = attribute_chain(value)
        return CallArgument(
            keyword=keyword,
            expression=".".join(chain) if chain else None,
            chain=chain,
            constant=_constant_of(value),
            location=SourceLocation.from_node(value),
            node=value,
        )

    def _record_attribute(self, node: ast.Attribute, scope: _Scope) -> None:
        chain = attribute_chain(node)
        self._attributes.append(
            AttributeAccess(
                attribute=node.attr,
                chain=chain,
                expression=".".join(chain) if chain else None,
                root=chain[0] if chain else None,
                location=SourceLocation.from_node(node),
                enclosing_function=scope.function,
                enclosing_class=scope.class_name,
                node=node,
            )
        )

    def _record_name(self, node: ast.Name, scope: _Scope) -> None:
        self._names.append(
            NameReference(
                name=node.id,
                context=_NAME_CONTEXTS.get(type(node.ctx), NameContext.LOAD),
                location=SourceLocation.from_node(node),
                enclosing_function=scope.function,
                enclosing_class=scope.class_name,
                node=node,
            )
        )

    def _record_assignment(
        self, node: ast.Assign | ast.AugAssign | ast.NamedExpr, scope: _Scope
    ) -> None:
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        names = tuple(_target_names(targets))
        self._assignments.append(
            Assignment(
                targets=names,
                value_expression=dotted_name(node.value),
                value_chain=attribute_chain(node.value),
                value_call=_callee_of(node.value),
                is_annotated=False,
                location=SourceLocation.from_node(node),
                enclosing_function=scope.function,
                enclosing_class=scope.class_name,
                node=node,
            )
        )
        self._record_variable_symbols(names, node, scope)

    def _record_annotated_assignment(self, node: ast.AnnAssign, scope: _Scope) -> None:
        names = tuple(_target_names([node.target]))
        self._assignments.append(
            Assignment(
                targets=names,
                value_expression=dotted_name(node.value) if node.value is not None else None,
                value_chain=attribute_chain(node.value) if node.value is not None else None,
                value_call=_callee_of(node.value) if node.value is not None else None,
                is_annotated=True,
                location=SourceLocation.from_node(node),
                enclosing_function=scope.function,
                enclosing_class=scope.class_name,
                node=node,
            )
        )
        self._annotations.append(
            self._build_annotation(names[0] if names else None, node.annotation, node, scope)
        )
        self._record_variable_symbols(names, node, scope)

    def _record_variable_symbols(
        self, names: tuple[str, ...], node: ast.AST, scope: _Scope
    ) -> None:
        """Record module-level and class-level bindings as symbols.

        Locals inside a function are left out: they are already in
        ``assignments`` and would drown the symbol table.
        """
        if scope.function is not None:
            return
        location = SourceLocation.from_node(node)
        for name in names:
            self._symbols.append(
                Symbol(
                    kind=SymbolKind.VARIABLE,
                    name=name,
                    qualified_name=scope.qualify(name),
                    path=self._path,
                    location=location,
                    parent=scope.prefix or None,
                    node=node,
                )
            )

    def _build_annotation(
        self, target: str | None, annotation: ast.expr, node: ast.AST, scope: _Scope
    ) -> Annotation:
        chain = attribute_chain(annotation)
        return Annotation(
            target=target,
            annotation_expression=".".join(chain) if chain else None,
            annotation_chain=chain,
            location=SourceLocation.from_node(node),
            enclosing_function=scope.function,
            enclosing_class=scope.class_name,
            node=node,
        )


def _target_names(targets: Iterable[ast.expr]) -> Iterator[str]:
    """Yield the assignable names in a target list, in source order.

    Tuple and list targets are unpacked one level; attribute and subscript
    targets are described by their dotted text where that is representable.
    """
    for target in targets:
        if isinstance(target, ast.Name):
            yield target.id
        elif isinstance(target, ast.Tuple | ast.List):
            yield from _target_names(target.elts)
        elif isinstance(target, ast.Attribute):
            dotted = dotted_name(target)
            if dotted is not None:
                yield dotted
            else:
                yield target.attr


def _join_module(prefix: str, name: str) -> str:
    """Join a module prefix and a member name, keeping relative dots intact."""
    if not prefix:
        return name
    if prefix.endswith("."):
        return f"{prefix}{name}"
    return f"{prefix}.{name}"


def _callee_of(node: ast.expr) -> str | None:
    """Return the dotted callee when the expression is a call, else None."""
    if not isinstance(node, ast.Call):
        return None
    return dotted_name(node.func)


def _constant_of(node: ast.expr) -> object | None:
    """Return a literal argument's value, or None when it is not a short literal.

    Only the value is copied, never evaluated. Long strings and bytes are left
    out so an untrusted file cannot be duplicated into the representation.
    """
    if not isinstance(node, ast.Constant):
        return None
    value = node.value
    if isinstance(value, str | bytes) and len(value) > MAX_CONSTANT_LENGTH:
        return None
    return value
