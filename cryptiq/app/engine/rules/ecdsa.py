"""PY-CRYPTO-ECDSA: ECDSA signatures in the ``cryptography`` library.

An elliptic-curve key is not by itself an ECDSA signature. The proof is the
``ec.ECDSA(...)`` argument passed to ``sign`` or ``verify``. Constructing a
curve, generating an EC key or exchanging with one is not reported here.
"""

from app.engine.rules.base import CryptoOperation
from app.engine.rules.marker import MarkerRule

RULE_ID = "PY-CRYPTO-ECDSA"
ALGORITHM = "ECDSA"
EC_MODULE = "cryptography.hazmat.primitives.asymmetric.ec"
ECDSA_MARKER = f"{EC_MODULE}.ECDSA"

METHOD_OPERATIONS = {
    "sign": CryptoOperation.SIGN,
    "verify": CryptoOperation.VERIFY,
}

EcdsaRule = MarkerRule(
    rule_id=RULE_ID,
    algorithm=ALGORITHM,
    primitive=ALGORITHM,
    marker=ECDSA_MARKER,
    method_operations=METHOD_OPERATIONS,
)
