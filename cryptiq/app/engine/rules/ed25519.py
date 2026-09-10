"""PY-CRYPTO-ED25519: Ed25519 signatures in the ``cryptography`` library.

Ed25519 is established by its namespace or its key classes, never by a method
name. ``key.sign(...)`` on an object the file does not establish as an Ed25519
key is not reported: the same method name belongs to RSA, ECDSA and several
non-cryptographic APIs.
"""

from app.engine.rules.base import CryptoOperation
from app.engine.rules.keypair import KeyPairRule
from app.engine.rules.resolution import KeyKind, NamespaceSpec

RULE_ID = "PY-CRYPTO-ED25519"
ALGORITHM = "Ed25519"
ED25519_MODULE = "cryptography.hazmat.primitives.asymmetric.ed25519"

SPEC = NamespaceSpec(
    modules=(ED25519_MODULE,),
    classes={
        "Ed25519PrivateKey": KeyKind.PRIVATE,
        "Ed25519PublicKey": KeyKind.PUBLIC,
    },
    constructors={
        "Ed25519PrivateKey.generate": KeyKind.PRIVATE,
        "Ed25519PrivateKey.from_private_bytes": KeyKind.PRIVATE,
        "Ed25519PublicKey.from_public_bytes": KeyKind.PUBLIC,
    },
    derivations={"public_key": (KeyKind.PRIVATE, KeyKind.PUBLIC)},
)

# Loading a key is not generating one; only ``generate`` creates key material.
MODULE_OPERATIONS = {
    "Ed25519PrivateKey.generate": CryptoOperation.KEY_GENERATION,
}

METHOD_OPERATIONS = {
    "sign": (CryptoOperation.SIGN, KeyKind.PRIVATE),
    "verify": (CryptoOperation.VERIFY, KeyKind.PUBLIC),
}

Ed25519Rule = KeyPairRule(
    rule_id=RULE_ID,
    algorithm=ALGORITHM,
    primitive=ALGORITHM,
    prefix="ed25519",
    spec=SPEC,
    module_operations=MODULE_OPERATIONS,
    method_operations=METHOD_OPERATIONS,
    canonical_class={
        KeyKind.PRIVATE: "Ed25519PrivateKey",
        KeyKind.PUBLIC: "Ed25519PublicKey",
    },
)
