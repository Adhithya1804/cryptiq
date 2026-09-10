"""PY-CRYPTO-HASH: hash algorithms from the ``cryptography`` library.

The rule records that a hash algorithm was named, and which one. It does not
decide whether that hash is appropriate: SHA-1 in a legacy checksum and SHA-1
in a signature are the same observation here and different decisions later.

A variable called ``SHA256``, a comment naming MD5 or a string containing
"sha1" produce nothing. The algorithm must resolve into the hashes namespace.
"""

import ast
from dataclasses import dataclass

from app.engine.engine import engine_versions
from app.engine.rules.base import (
    AnalysisContext,
    Call,
    CryptoOperation,
    EvidenceBasis,
    MatchConfidence,
    RuleMatch,
)
from app.engine.rules.resolution import member_of, resolve_chain

RULE_ID = "PY-CRYPTO-HASH"
PRIMITIVE = "HASH"
LIBRARY = "cryptography"

HASHES_MODULE = "cryptography.hazmat.primitives.hashes"

# The class name as written in the library, mapped to the algorithm's usual
# spelling. The right-hand side is what the rest of the engine matches on, so
# it is kept in the form the standards use.
HASH_ALGORITHMS: dict[str, str] = {
    "MD5": "MD5",
    "SHA1": "SHA-1",
    "SHA224": "SHA-224",
    "SHA256": "SHA-256",
    "SHA384": "SHA-384",
    "SHA512": "SHA-512",
    "SHA512_224": "SHA-512/224",
    "SHA512_256": "SHA-512/256",
    "SHA3_224": "SHA3-224",
    "SHA3_256": "SHA3-256",
    "SHA3_384": "SHA3-384",
    "SHA3_512": "SHA3-512",
    "SHAKE128": "SHAKE128",
    "SHAKE256": "SHAKE256",
    "BLAKE2b": "BLAKE2b",
    "BLAKE2s": "BLAKE2s",
    "SM3": "SM3",
}


@dataclass(frozen=True)
class HashRule:
    """Recognises a named hash algorithm."""

    rule_id: str = RULE_ID

    @property
    def version(self) -> str:
        """The configured rule set version, stamped on every match."""
        return engine_versions().ruleset_version

    def evaluate(self, node: ast.AST, context: AnalysisContext) -> RuleMatch | None:
        """Return a hash observation for a call node, or None."""
        call = context.call(node)
        if call is None or call.chain is None:
            return None

        member = member_of(HASHES_MODULE, resolve_chain(context.file, call.chain))
        algorithm = HASH_ALGORITHMS.get(member) if member else None
        if algorithm is None:
            return None

        return self._match(call, algorithm=algorithm, member=member)

    def _match(self, call: Call, *, algorithm: str, member: str) -> RuleMatch:
        return RuleMatch(
            rule_id=self.rule_id,
            ruleset_version=self.version,
            algorithm=algorithm,
            primitive=PRIMITIVE,
            library=LIBRARY,
            api=f"hashes.{member}",
            operation=CryptoOperation.HASH,
            file_path=call.path,
            location=call.location,
            confidence=MatchConfidence.HIGH,
            evidence_basis=EvidenceBasis.DIRECT_MODULE_API,
            enclosing_function=call.enclosing_function,
            enclosing_class=call.enclosing_class,
            node=call.node,
        )
