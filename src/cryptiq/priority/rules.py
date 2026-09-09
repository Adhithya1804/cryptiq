"""Deterministic evaluation rules and constants for Migration Review Priority."""

from typing import Set

# Asymmetric algorithms broken by Shor's algorithm
ASYMMETRIC_ALGORITHMS: Set[str] = {
    "RSA",
    "ECDSA",
    "ED25519",
    "ED448",
    "EDDSA",
    "ECDH",
    "X25519",
    "X448",
    "DH",
    "DIFFIE-HELLMAN",
    "DSA",
    "ECC",
    "ELGAMAL",
}

# Post-quantum primitives already resistant
PQC_NATIVE_ALGORITHMS: Set[str] = {
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

# Symmetric primitives
SYMMETRIC_ALGORITHMS: Set[str] = {
    "AES",
    "CHACHA20",
    "3DES",
    "DES",
    "BLOWFISH",
    "ARC4",
    "RC4",
}

# Hash primitives
HASH_ALGORITHMS: Set[str] = {
    "SHA-256",
    "SHA-384",
    "SHA-512",
    "SHA-224",
    "SHA-3",
    "SHA-1",
    "MD5",
    "BLAKE2B",
    "BLAKE2S",
}

# Legacy hash primitives with known classical collision issues
LEGACY_HASH_ALGORITHMS: Set[str] = {
    "SHA-1",
    "MD5",
}
