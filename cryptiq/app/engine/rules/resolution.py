"""Shared deterministic resolution helpers for the cryptographic rules.

Every rule answers the same two questions: does this dotted expression resolve
into a known cryptographic namespace, and does this local name provably hold a
key of a known kind. Both answers come from the parser's import index and from
assignments and annotations inside a single function scope. Nothing here
crosses a function boundary, follows data flow, or executes anything.
"""

import ast
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from enum import StrEnum

from app.engine.parser import ParsedFile, SymbolKind
from app.engine.rules.base import EvidenceBasis, MatchConfidence


class KeyKind(StrEnum):
    """Which half of an asymmetric key pair, or which cipher context, a name holds."""

    PRIVATE = "PRIVATE"
    PUBLIC = "PUBLIC"
    CIPHER = "CIPHER"
    AEAD = "AEAD"


Scope = str | None
BindingKey = tuple[Scope, str]


def resolve_chain(file: ParsedFile, chain: Iterable[str] | None) -> str | None:
    """Resolve a dotted chain against the file's imports.

    The root is looked up in the import index and the rest of the chain is
    appended, so ``ec.ECDSA`` and the fully spelled
    ``cryptography.hazmat.primitives.asymmetric.ec.ECDSA`` resolve to the same
    path. A root that was never imported gives None.
    """
    parts = tuple(chain or ())
    if not parts:
        return None
    target = file.resolve(parts[0])
    if target is None:
        return None
    return ".".join((target, *parts[1:]))


def resolve_dotted(file: ParsedFile, dotted: str | None) -> str | None:
    """Resolve a dotted expression written as text."""
    if not dotted:
        return None
    return resolve_chain(file, dotted.split("."))


def member_of(module: str, path: str | None) -> str | None:
    """Return what a resolved path names inside a module, or None."""
    if path is None:
        return None
    prefix = f"{module}."
    if not path.startswith(prefix):
        return None
    return path[len(prefix) :]


def member_of_any(modules: Iterable[str], path: str | None) -> str | None:
    """Return the member name if a path sits inside any of the modules."""
    for module in modules:
        member = member_of(module, path)
        if member is not None:
            return member
    return None


def is_class_body(enclosing_function: Scope, enclosing_class: str | None) -> bool:
    """True when a binding sits directly in a class body.

    A class attribute is not visible as a bare name inside the class's own
    methods, so such a binding must not enter any function scope.
    """
    if enclosing_class is None:
        return False
    if enclosing_function is None:
        return True
    return enclosing_class.startswith(f"{enclosing_function}.")


@dataclass(frozen=True)
class NamespaceSpec:
    """What one rule considers evidence of its algorithm.

    ``classes`` names the key classes and the half of the pair each denotes.
    ``constructors`` names members of the module -- a function, or a class
    method written as ``Class.method`` -- that return a key of a given kind.
    ``derivations`` names a method that turns one established kind into
    another, such as ``public_key`` on a private key.
    """

    modules: tuple[str, ...]
    classes: Mapping[str, KeyKind] = field(default_factory=dict)
    constructors: Mapping[str, KeyKind] = field(default_factory=dict)
    derivations: Mapping[str, tuple[KeyKind, KeyKind]] = field(default_factory=dict)

    def member(self, file: ParsedFile, chain: Iterable[str] | None) -> str | None:
        """Return what a chain names inside this rule's namespace, or None."""
        return member_of_any(self.modules, resolve_chain(file, chain))

    def class_kind(self, member: str | None) -> KeyKind | None:
        """Return the kind a class name denotes, or None."""
        return self.classes.get(member) if member else None


@dataclass(frozen=True)
class Binding:
    """An established local name and the evidence that established it."""

    kind: KeyKind
    basis: EvidenceBasis
    confidence: MatchConfidence


@dataclass(frozen=True)
class _Established:
    """One assignment's outcome."""

    kind: KeyKind
    basis: EvidenceBasis


@dataclass
class BindingIndex:
    """Which local names hold a key of a known kind, per scope, for one file.

    Lookup walks outwards through enclosing *function* scopes only. A class
    body is skipped, because its names are not visible as bare names inside
    its methods. A name bound locally by something the rule could not
    establish stops the walk, so an unannotated parameter never inherits a
    module-level binding of the same name.
    """

    bindings: dict[BindingKey, Binding] = field(default_factory=dict)
    locally_bound: dict[Scope, set[str]] = field(default_factory=dict)
    function_scopes: set[str] = field(default_factory=set)

    def lookup(self, scope: Scope, name: str) -> Binding | None:
        """Return what a name provably holds in a scope, or None."""
        for level in self.scope_chain(scope):
            binding = self.bindings.get((level, name))
            if binding is not None:
                return binding
            if name in self.locally_bound.get(level, ()):
                return None
        return None

    def scope_chain(self, scope: Scope) -> list[Scope]:
        """Return the function scopes a name lookup may walk, innermost first."""
        chain: list[Scope] = []
        current = scope
        while current:
            if current in self.function_scopes:
                chain.append(current)
            current = current.rsplit(".", 1)[0] if "." in current else None
        chain.append(None)
        return chain


def build_index(file: ParsedFile, spec: NamespaceSpec) -> BindingIndex:
    """Index the names that provably hold a key of this rule's algorithm."""
    index = BindingIndex()
    collect_scopes(file, index)
    _collect_annotations(file, spec, index)
    _collect_assignments(file, spec, index)
    return index


def collect_scopes(file: ParsedFile, index: BindingIndex) -> None:
    """Record function scopes and every name bound inside each of them."""
    for kind in (SymbolKind.FUNCTION, SymbolKind.ASYNC_FUNCTION):
        for symbol in file.symbols_of(kind):
            index.function_scopes.add(symbol.qualified_name)
            if isinstance(symbol.node, ast.FunctionDef | ast.AsyncFunctionDef):
                bound = index.locally_bound.setdefault(symbol.qualified_name, set())
                bound.update(_parameter_names(symbol.node.args))

    for reference in file.names:
        if reference.context.value in {"STORE", "DELETE"}:
            index.locally_bound.setdefault(reference.enclosing_function, set()).add(
                reference.name
            )


def _parameter_names(arguments: ast.arguments) -> set[str]:
    names = {
        argument.arg
        for group in (arguments.posonlyargs, arguments.args, arguments.kwonlyargs)
        for argument in group
    }
    for extra in (arguments.vararg, arguments.kwarg):
        if extra is not None:
            names.add(extra.arg)
    return names


def _collect_annotations(file: ParsedFile, spec: NamespaceSpec, index: BindingIndex) -> None:
    """Bind names annotated with one of the rule's key classes.

    Supports ``key: Ed25519PrivateKey`` and ``key: ed25519.Ed25519PrivateKey``,
    on a parameter or on an annotated assignment. A class-level annotation is
    skipped: it declares an attribute, not a bare name. Two annotations that
    disagree about the same name cancel each other out.
    """
    found: dict[BindingKey, set[KeyKind]] = {}
    for annotation in file.annotations:
        if annotation.target is None or not annotation.target.isidentifier():
            continue
        if is_class_body(annotation.enclosing_function, annotation.enclosing_class):
            continue
        kind = spec.class_kind(spec.member(file, annotation.annotation_chain))
        if kind is None:
            continue
        found.setdefault((annotation.enclosing_function, annotation.target), set()).add(kind)

    for key, kinds in found.items():
        if len(kinds) == 1:
            index.bindings[key] = Binding(
                kind=kinds.pop(),
                basis=EvidenceBasis.CLASS_ANNOTATION,
                confidence=MatchConfidence.HIGH,
            )


def _collect_assignments(file: ParsedFile, spec: NamespaceSpec, index: BindingIndex) -> None:
    """Bind names assigned from one of the rule's constructors.

    Three forms are supported, all purely local and all a single hop:

    * ``key = Ed25519PrivateKey.generate()`` binds a private key.
    * ``public = key.public_key()`` binds a public key, but only when ``key``
      is already established in the same scope chain.
    * ``alias = key`` carries an established binding to another name.

    The last two read only bindings established before them, never each other,
    so no chain of inferences can form. A name assigned anywhere in its scope
    from something the rule cannot establish is left unbound. An annotation,
    being stronger evidence, is not overridden here.
    """
    candidates = [
        (assignment, assignment.targets[0], assignment.enclosing_function)
        for assignment in file.assignments
        if len(assignment.targets) == 1
        and assignment.targets[0].isidentifier()
        and not is_class_body(assignment.enclosing_function, assignment.enclosing_class)
    ]

    direct: dict[BindingKey, _Established | None] = {}
    for assignment, name, scope in candidates:
        merge(direct, (scope, name), _constructed(file, spec, assignment.value_call))

    combined = dict(direct)
    for assignment, name, scope in candidates:
        if _constructed(file, spec, assignment.value_call) is not None:
            continue
        established = _derived(index, spec, direct, scope, assignment.value_call) or _aliased(
            index, direct, scope, assignment.value_expression
        )
        # Merged unconditionally: an assignment this round cannot establish
        # must still be able to erase a name the round established elsewhere.
        merge(combined, (scope, name), established, replace_unknown=True)

    for key, established in combined.items():
        if established is None or key in index.bindings:
            continue
        index.bindings[key] = Binding(
            kind=established.kind,
            basis=established.basis,
            confidence=MatchConfidence.MEDIUM,
        )


def merge(
    table: dict[BindingKey, _Established | None],
    key: BindingKey,
    established: _Established | None,
    *,
    replace_unknown: bool = False,
) -> None:
    """Record an assignment's outcome, letting a disagreement erase the name."""
    if key not in table:
        table[key] = established
        return
    existing = table[key]
    if existing is not None and established is not None and existing.kind is established.kind:
        return
    if existing == established:
        return
    if replace_unknown and existing is None:
        table[key] = established
        return
    table[key] = None


def _constructed(
    file: ParsedFile, spec: NamespaceSpec, value_call: str | None
) -> _Established | None:
    """Return the key a constructor call produces, if it is one of the rule's."""
    if value_call is None:
        return None
    member = spec.member(file, value_call.split("."))
    kind = spec.constructors.get(member) if member else None
    if kind is None:
        return None
    return _Established(kind, EvidenceBasis.CONSTRUCTOR_ASSIGNMENT)


def established_kind(
    index: BindingIndex,
    direct: dict[BindingKey, _Established | None],
    scope: Scope,
    name: str,
) -> KeyKind | None:
    """Return the kind already established for a name, or None."""
    binding = index.lookup(scope, name)
    if binding is not None:
        return binding.kind
    prior = direct.get((scope, name))
    return prior.kind if prior is not None else None


def _derived(
    index: BindingIndex,
    spec: NamespaceSpec,
    direct: dict[BindingKey, _Established | None],
    scope: Scope,
    value_call: str | None,
) -> _Established | None:
    """Return the kind a derivation produces from an established receiver."""
    if value_call is None:
        return None
    parts = value_call.split(".")
    if len(parts) != 2:
        return None
    derivation = spec.derivations.get(parts[1])
    if derivation is None:
        return None
    source_kind, target_kind = derivation
    if established_kind(index, direct, scope, parts[0]) is not source_kind:
        return None
    return _Established(target_kind, EvidenceBasis.CONSTRUCTOR_ASSIGNMENT)


def _aliased(
    index: BindingIndex,
    direct: dict[BindingKey, _Established | None],
    scope: Scope,
    value_expression: str | None,
) -> _Established | None:
    """Return the kind of ``alias = established_name``, else None."""
    if value_expression is None or not value_expression.isidentifier():
        return None
    kind = established_kind(index, direct, scope, value_expression)
    if kind is None:
        return None
    return _Established(kind, EvidenceBasis.ESTABLISHED_ALIAS)


def names_assigned_from(
    file: ParsedFile, resolved_callee: str
) -> dict[BindingKey, bool]:
    """Map local names to whether they provably hold ``resolved_callee(...)``.

    Used by the rules whose evidence is a marker object rather than a key, such
    as ``algorithm = ec.ECDSA(...)``. A name assigned anywhere in its scope
    from something else maps to False and is never claimed.
    """
    outcome: dict[BindingKey, bool] = {}
    for assignment in file.assignments:
        if len(assignment.targets) != 1 or not assignment.targets[0].isidentifier():
            continue
        if is_class_body(assignment.enclosing_function, assignment.enclosing_class):
            continue
        key = (assignment.enclosing_function, assignment.targets[0])
        matches = resolve_dotted(file, assignment.value_call) == resolved_callee
        outcome[key] = matches if key not in outcome else outcome[key] and matches
    return outcome
