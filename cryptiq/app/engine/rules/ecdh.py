"""PY-CRYPTO-ECDH: elliptic-curve key agreement in the ``cryptography`` library.

The proof is the ``ec.ECDH()`` argument passed to ``exchange``. A method named
``exchange`` on anything else establishes nothing, and an EC key used for
signing is not a key agreement.
"""

from app.engine.rules.base import CryptoOperation
from app.engine.rules.ecdsa import EC_MODULE
from app.engine.rules.marker import MarkerRule

RULE_ID = "PY-CRYPTO-ECDH"
ALGORITHM = "ECDH"
ECDH_MARKER = f"{EC_MODULE}.ECDH"

METHOD_OPERATIONS = {
    "exchange": CryptoOperation.KEY_ESTABLISHMENT,
}

EcdhRule = MarkerRule(
    rule_id=RULE_ID,
    algorithm=ALGORITHM,
    primitive=ALGORITHM,
    marker=ECDH_MARKER,
    method_operations=METHOD_OPERATIONS,
)
