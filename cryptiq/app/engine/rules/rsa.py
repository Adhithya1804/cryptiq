"""PY-CRYPTO-RSA: RSA usage in the Python ``cryptography`` library.

The rule reads syntax, never text. A construct is RSA only when the AST shows
it: an import that resolves to the RSA namespace, an RSA class named in an
annotation, or a local name assigned directly from an RSA constructor. A
receiver whose type cannot be established produces nothing, so ``key.sign(...)``
on an unknown object is never reported.
"""

import ast

from app.engine.engine import engine_versions
from app.engine.rules.base import (
    AnalysisContext,
    Call,
    CryptoOperation,
    EvidenceBasis,
    MatchConfidence,
    RuleMatch,
)
from app.engine.rules.resolution import KeyKind, NamespaceSpec

RULE_ID = "PY-CRYPTO-RSA"
ALGORITHM = "RSA"
PRIMITIVE = "RSA"
LIBRARY = "cryptography"

# The one public RSA namespace. Internal binding namespaces such as
# ``cryptography.hazmat.bindings._rust.openssl.rsa`` are deliberately not
# covered: they are implementation detail, not an API a project calls.
RSA_MODULE = "cryptography.hazmat.primitives.asymmetric.rsa"

# Module-level callables that are themselves a cryptographic operation. The
# key-material helpers in the same module (rsa_crt_iqmp and friends) are not
# operations and are left out.
MODULE_OPERATIONS: dict[str, CryptoOperation] = {
    "generate_private_key": CryptoOperation.KEY_GENERATION,
}

# Key methods, and the half of the key pair each one requires. A method called
# on the wrong half is not reported: the evidence contradicts itself.
METHOD_OPERATIONS: dict[str, tuple[CryptoOperation, KeyKind]] = {
    "sign": (CryptoOperation.SIGN, KeyKind.PRIVATE),
    "decrypt": (CryptoOperation.DECRYPT, KeyKind.PRIVATE),
    "verify": (CryptoOperation.VERIFY, KeyKind.PUBLIC),
    "encrypt": (CryptoOperation.ENCRYPT, KeyKind.PUBLIC),
}

CANONICAL_CLASS = {KeyKind.PRIVATE: "RSAPrivateKey", KeyKind.PUBLIC: "RSAPublicKey"}

SPEC = NamespaceSpec(
    modules=(RSA_MODULE,),
    classes={
        "RSAPrivateKey": KeyKind.PRIVATE,
        "RSAPrivateKeyWithSerialization": KeyKind.PRIVATE,
        "RSAPublicKey": KeyKind.PUBLIC,
        "RSAPublicKeyWithSerialization": KeyKind.PUBLIC,
    },
    constructors={"generate_private_key": KeyKind.PRIVATE},
    # The one derivation the rule follows: a public key taken from an
    # established private key.
    derivations={"public_key": (KeyKind.PRIVATE, KeyKind.PUBLIC)},
)


class RsaRule:
    """Recognises RSA usage from the ``cryptography`` library."""

    rule_id = RULE_ID

    @property
    def version(self) -> str:
        """The configured rule set version, stamped on every match."""
        return engine_versions().ruleset_version

    def evaluate(self, node: ast.AST, context: AnalysisContext) -> RuleMatch | None:
        """Return an RSA observation for a call node, or None."""
        call = context.call(node)
        if call is None or call.chain is None:
            return None

        return self._imported_api(call, context) or self._receiver_api(call, context)

    def _imported_api(self, call: Call, context: AnalysisContext) -> RuleMatch | None:
        """Match a call whose callable resolves into the RSA module itself."""
        member = SPEC.member(context.file, call.chain)
        if member is None:
            return None

        operation = MODULE_OPERATIONS.get(member)
        if operation is not None:
            return self._match(
                call,
                api=f"rsa.{member}",
                operation=operation,
                confidence=MatchConfidence.HIGH,
                basis=EvidenceBasis.DIRECT_MODULE_API,
            )

        class_name, _, method = member.partition(".")
        kind = SPEC.class_kind(class_name)
        entry = METHOD_OPERATIONS.get(method)
        if kind is None or entry is None or entry[1] is not kind:
            return None
        return self._match(
            call,
            api=f"{class_name}.{method}",
            operation=entry[0],
            confidence=MatchConfidence.HIGH,
            basis=EvidenceBasis.CLASS_IMPORT,
        )

    def _receiver_api(self, call: Call, context: AnalysisContext) -> RuleMatch | None:
        """Match a key method on a local name established as an RSA key."""
        if len(call.chain) != 2:
            return None
        entry = METHOD_OPERATIONS.get(call.chain[1])
        if entry is None:
            return None
        operation, required = entry

        binding = context.index(self.rule_id, SPEC).lookup(
            call.enclosing_function, call.chain[0]
        )
        if binding is None or binding.kind is not required:
            return None

        return self._match(
            call,
            api=f"{CANONICAL_CLASS[binding.kind]}.{call.chain[1]}",
            operation=operation,
            confidence=binding.confidence,
            basis=binding.basis,
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
            primitive=PRIMITIVE,
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
