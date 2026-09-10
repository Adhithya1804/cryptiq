"""Golden fixture: ECDSA verification."""

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric.ec import ECDSA


def verify_with_imported_marker(public_key, signature, payload):
    return public_key.verify(signature, payload, ECDSA(hashes.SHA256()))


def verify_with_assigned_marker(public_key, signature, payload):
    algorithm = ECDSA(hashes.SHA256())
    return public_key.verify(signature, payload, algorithm)


def verify_with_an_ambiguous_marker(public_key, signature, payload, flag):
    """The name is overwritten by something unknown, so nothing is claimed."""
    algorithm = ECDSA(hashes.SHA256())
    if flag:
        algorithm = load()
    return public_key.verify(signature, payload, algorithm)


def verify_without_a_marker(public_key, signature, payload):
    return public_key.verify(signature, payload)
