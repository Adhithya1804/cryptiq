"""PY-CRYPTO-AES: AES usage in the ``cryptography`` library.

AES is established by the namespace the algorithm class comes from, never by a
variable called ``AES`` or a method called ``encrypt``. Three things are
reported: naming the algorithm, and encrypting or decrypting through a context
built from it.

Nothing here judges whether the use is safe. A mode, a key length or a nonce
policy is a later decision; this rule only records that AES is present.
"""

import ast
from dataclasses import dataclass

from app.engine.engine import engine_versions
from app.engine.parser import ParsedFile, attribute_chain
from app.engine.rules.base import (
    AnalysisContext,
    Call,
    CryptoOperation,
    EvidenceBasis,
    MatchConfidence,
    RuleMatch,
)
from app.engine.rules.resolution import (
    BindingKey,
    KeyKind,
    is_class_body,
    member_of,
    resolve_chain,
    resolve_dotted,
)

RULE_ID = "PY-CRYPTO-AES"
ALGORITHM = "AES"
LIBRARY = "cryptography"

CIPHERS_MODULE = "cryptography.hazmat.primitives.ciphers"
ALGORITHMS_MODULE = f"{CIPHERS_MODULE}.algorithms"
AEAD_MODULE = f"{CIPHERS_MODULE}.aead"
CIPHER_CLASS = f"{CIPHERS_MODULE}.Cipher"

# The block-cipher algorithm classes, used to build a Cipher.
BLOCK_ALGORITHMS = frozenset({"AES", "AES128", "AES256"})

# The one-shot authenticated modes, which are their own context.
AEAD_ALGORITHMS = frozenset({"AESGCM", "AESGCMSIV", "AESCCM", "AESSIV", "AESOCB3"})

# Methods that turn a context into an operation on data.
CIPHER_METHODS = {
    "encryptor": CryptoOperation.ENCRYPT,
    "decryptor": CryptoOperation.DECRYPT,
}
AEAD_METHODS = {
    "encrypt": CryptoOperation.ENCRYPT,
    "decrypt": CryptoOperation.DECRYPT,
}


@dataclass(frozen=True)
class AesRule:
    """Recognises AES construction and the operations built from it."""

    rule_id: str = RULE_ID

    @property
    def version(self) -> str:
        """The configured rule set version, stamped on every match."""
        return engine_versions().ruleset_version

    def evaluate(self, node: ast.AST, context: AnalysisContext) -> RuleMatch | None:
        """Return an AES observation for a call node, or None."""
        call = context.call(node)
        if call is None:
            return None
        return self._construction(call, context) or self._context_method(call, context)

    def _construction(self, call: Call, context: AnalysisContext) -> RuleMatch | None:
        """Match a call that names an AES algorithm class."""
        resolved = resolve_chain(context.file, call.chain)
        member = member_of(ALGORITHMS_MODULE, resolved)
        if member in BLOCK_ALGORITHMS:
            return self._match(
                call,
                api=f"algorithms.{member}",
                operation=CryptoOperation.CONSTRUCTION,
                confidence=MatchConfidence.HIGH,
                basis=EvidenceBasis.DIRECT_MODULE_API,
            )

        member = member_of(AEAD_MODULE, resolved)
        if member in AEAD_ALGORITHMS:
            return self._match(
                call,
                api=f"aead.{member}",
                operation=CryptoOperation.CONSTRUCTION,
                confidence=MatchConfidence.HIGH,
                basis=EvidenceBasis.DIRECT_MODULE_API,
            )
        return None

    def _context_method(self, call: Call, context: AnalysisContext) -> RuleMatch | None:
        """Match an operation on a local name established as an AES context."""
        if call.chain is None or len(call.chain) != 2:
            return None
        receiver, method = call.chain

        index = context.cached(f"{self.rule_id}:contexts", _build_contexts)
        kind = index.get((call.enclosing_function, receiver)) or index.get((None, receiver))
        if kind is None:
            return None

        methods = CIPHER_METHODS if kind is KeyKind.CIPHER else AEAD_METHODS
        operation = methods.get(method)
        if operation is None:
            return None

        return self._match(
            call,
            api=f"{'Cipher' if kind is KeyKind.CIPHER else 'AESAEAD'}.{method}",
            operation=operation,
            confidence=MatchConfidence.MEDIUM,
            basis=EvidenceBasis.CONSTRUCTOR_ASSIGNMENT,
        )

    def _match(
        self,
        call: Call,
        *,
        api: str,
        operation: CryptoOperation,
        confidence: MatchConfidence,
        basis: EvidenceBasis,
    ) -> RuleMatch:
        return RuleMatch(
            rule_id=self.rule_id,
            ruleset_version=self.version,
            algorithm=ALGORITHM,
            primitive=ALGORITHM,
            library=LIBRARY,
            api=api,
            operation=operation,
            file_path=call.path,
            location=call.location,
            confidence=confidence,
            evidence_basis=basis,
            enclosing_function=call.enclosing_function,
            enclosing_class=call.enclosing_class,
            node=call.node,
        )


def _build_contexts(file: ParsedFile) -> dict[BindingKey, KeyKind]:
    """Index the local names that hold an AES cipher or AEAD context.

    Two forms, both a single hop inside one scope:

    * ``cipher = Cipher(algorithms.AES(key), mode)`` -- the Cipher call counts
      only when one of its arguments is itself an AES algorithm, so a Cipher
      built from ChaCha20 or Camellia is not claimed.
    * ``aesgcm = AESGCM(key)`` -- an authenticated mode is its own context.

    A name assigned anywhere in its scope from something else is dropped, so a
    reassigned name is never claimed.
    """
    established: dict[BindingKey, KeyKind | None] = {}
    for assignment in file.assignments:
        if len(assignment.targets) != 1 or not assignment.targets[0].isidentifier():
            continue
        if is_class_body(assignment.enclosing_function, assignment.enclosing_class):
            continue
        key = (assignment.enclosing_function, assignment.targets[0])
        kind = _context_kind(file, assignment)
        if key in established and established[key] is not kind:
            established[key] = None
        else:
            established[key] = kind

    return {key: kind for key, kind in established.items() if kind is not None}


def _context_kind(file: ParsedFile, assignment) -> KeyKind | None:
    """Return the kind of AES context an assignment builds, if any."""
    resolved = resolve_dotted(file, assignment.value_call)
    if resolved is None:
        return None

    if resolved == CIPHER_CLASS:
        return KeyKind.CIPHER if _uses_aes_algorithm(file, assignment.node) else None

    member = member_of(AEAD_MODULE, resolved)
    return KeyKind.AEAD if member in AEAD_ALGORITHMS else None


def _uses_aes_algorithm(file: ParsedFile, node: ast.AST) -> bool:
    """True when a Cipher call is built from an AES algorithm class."""
    value = getattr(node, "value", None)
    if not isinstance(value, ast.Call):
        return False
    for argument in value.args:
        if not isinstance(argument, ast.Call):
            continue
        member = member_of(ALGORITHMS_MODULE, resolve_chain(file, attribute_chain(argument.func)))
        if member in BLOCK_ALGORITHMS:
            return True
    return False
