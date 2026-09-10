"""Golden fixture: hash algorithms named through the hashes namespace."""

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives import hashes as h
from cryptography.hazmat.primitives.hashes import SHA256


def modern_hashes():
    return hashes.SHA256(), hashes.SHA384(), hashes.SHA512()


def legacy_hashes():
    """Recorded, not judged. Whether SHA-1 is acceptable here is a later call."""
    return hashes.SHA1(), hashes.MD5()


def sha3_family():
    return hashes.SHA3_256(), hashes.SHA3_512()


def blake_family():
    return hashes.BLAKE2b(64), hashes.BLAKE2s(32)


def aliased_module():
    return h.SHA256()


def imported_class():
    return SHA256()


def used_inside_a_digest(payload):
    digest = hashes.Hash(hashes.SHA256())
    digest.update(payload)
    return digest.finalize()


def a_variable_named_sha256():
    SHA256 = object()
    return SHA256


def a_string_and_a_comment():
    # MD5 and SHA256 named in a comment only.
    return "SHA256", "hashes.MD5"


def an_unrelated_sha256(library, payload):
    return library.SHA256(payload)
