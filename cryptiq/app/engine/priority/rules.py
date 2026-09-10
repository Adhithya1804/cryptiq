"""The algorithm tables the priority engine reads.

Membership is a statement about the algorithm family, not about a particular
use of it. The tables are data, kept apart from the scoring so a reviewer can
audit them without reading the logic.
"""

# Public-key algorithms broken by a cryptographically relevant quantum
# computer. These are the migration candidates.
ASYMMETRIC_ALGORITHMS = frozenset(
    {
        "RSA",
        "DSA",
        "ECDSA",
        "ECDH",
        "ED25519",
        "ED448",
        "EDDSA",
        "X25519",
        "X448",
        "DH",
        "DIFFIE-HELLMAN",
        "ECC",
        "ELGAMAL",
    }
)

# Already quantum-resistant. Present so a scan of a modernised codebase does
# not raise its own migration targets.
PQC_ALGORITHMS = frozenset(
    {
        "ML-KEM",
        "ML-DSA",
        "SLH-DSA",
        "KYBER",
        "DILITHIUM",
        "FALCON",
        "SPHINCS+",
        "XMSS",
        "LMS",
    }
)

# Symmetric primitives. Weakened by Grover, not broken by Shor, so they are a
# key-length review rather than a migration.
SYMMETRIC_ALGORITHMS = frozenset(
    {
        "AES",
        "CHACHA20",
        "3DES",
        "DES",
        "BLOWFISH",
        "RC4",
        "ARC4",
    }
)

# Hashes. Not directly quantum-vulnerable in the way public-key algorithms are.
HASH_ALGORITHMS = frozenset(
    {
        "SHA-1",
        "SHA-224",
        "SHA-256",
        "SHA-384",
        "SHA-512",
        "SHA-3",
        "SHA3-224",
        "SHA3-256",
        "SHA3-384",
        "SHA3-512",
        "SHAKE128",
        "SHAKE256",
        "SM3",
        "MD5",
        "BLAKE2B",
        "BLAKE2S",
    }
)

# Hashes with known classical weaknesses, worth flagging on their own merits.
LEGACY_HASH_ALGORITHMS = frozenset({"SHA-1", "MD5", "MD4"})
