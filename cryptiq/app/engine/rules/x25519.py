"""PY-CRYPTO-X25519: X25519 key agreement in the ``cryptography`` library.

A method named ``exchange`` establishes nothing on its own. X25519 is reported
only when the receiver is an established X25519 private key, or when the call
resolves into the X25519 namespace directly.
"""

from app.engine.rules.base import CryptoOperation
from app.engine.rules.keypair import KeyPairRule
from app.engine.rules.resolution import KeyKind, NamespaceSpec

RULE_ID = "PY-CRYPTO-X25519"
ALGORITHM = "X25519"
X25519_MODULE = "cryptography.hazmat.primitives.asymmetric.x25519"

SPEC = NamespaceSpec(
    modules=(X25519_MODULE,),
    classes={
        "X25519PrivateKey": KeyKind.PRIVATE,
        "X25519PublicKey": KeyKind.PUBLIC,
    },
    constructors={
        "X25519PrivateKey.generate": KeyKind.PRIVATE,
        "X25519PrivateKey.from_private_bytes": KeyKind.PRIVATE,
        "X25519PublicKey.from_public_bytes": KeyKind.PUBLIC,
    },
    derivations={"public_key": (KeyKind.PRIVATE, KeyKind.PUBLIC)},
)

MODULE_OPERATIONS = {
    "X25519PrivateKey.generate": CryptoOperation.KEY_GENERATION,
}

# X25519 takes only the peer's public key; there is no separate algorithm
# argument, so the receiver is the whole of the evidence.
METHOD_OPERATIONS = {
    "exchange": (CryptoOperation.KEY_ESTABLISHMENT, KeyKind.PRIVATE),
}

X25519Rule = KeyPairRule(
    rule_id=RULE_ID,
    algorithm=ALGORITHM,
    primitive=ALGORITHM,
    prefix="x25519",
    spec=SPEC,
    module_operations=MODULE_OPERATIONS,
    method_operations=METHOD_OPERATIONS,
    canonical_class={
        KeyKind.PRIVATE: "X25519PrivateKey",
        KeyKind.PUBLIC: "X25519PublicKey",
    },
)
