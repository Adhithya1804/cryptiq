"""Golden fixture: ECDSA signing, proved by the ec.ECDSA argument."""

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric import ec as elliptic


def sign_with_direct_marker(private_key, payload):
    return private_key.sign(payload, ec.ECDSA(hashes.SHA256()))


def sign_with_aliased_module(private_key, payload):
    return private_key.sign(payload, elliptic.ECDSA(hashes.SHA256()))


def sign_with_assigned_marker(private_key, payload):
    algorithm = ec.ECDSA(hashes.SHA256())
    return private_key.sign(payload, algorithm)


def sign_on_a_chained_receiver(container, payload):
    """The receiver is a call; the marker still proves the algorithm."""
    return container.key().sign(payload, ec.ECDSA(hashes.SHA256()))


def generate_a_curve_only():
    """Building a curve or an EC key is not an ECDSA signature."""
    curve = ec.SECP256R1()
    return ec.generate_private_key(curve)


def sign_without_a_marker(private_key, payload):
    return private_key.sign(payload)


def sign_something_unrelated(builder, payload):
    return builder.sign(payload, "ECDSA")
