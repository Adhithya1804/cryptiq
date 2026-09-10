"""Golden fixture: RSA encryption on an established public key."""

from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPublicKey


def encrypt_with_annotation(public_key: RSAPublicKey, payload):
    return public_key.encrypt(payload, padding.OAEP())


def encrypt_on_a_chained_call(payload):
    """The receiver is a call, not a name, so only the generation is reported."""
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return private_key.public_key().encrypt(payload, padding.OAEP())


def encrypt_with_assigned_derived_key(payload):
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_key = private_key.public_key()
    return public_key.encrypt(payload, padding.OAEP())


def encrypt_symmetric(cipher, payload):
    """A generic encrypt call on an unknown object is not RSA."""
    return cipher.encrypt(payload)
