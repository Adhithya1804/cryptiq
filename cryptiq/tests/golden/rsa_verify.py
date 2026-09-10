"""Golden fixture: RSA verification on an established public key."""

from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPublicKey


def verify_with_annotation(public_key: RSAPublicKey, signature, payload):
    return public_key.verify(signature, payload)


def verify_with_derived_key(signature, payload):
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_key = private_key.public_key()
    return public_key.verify(signature, payload)


def verify_wrong_half(private_key: rsa.RSAPrivateKey, signature, payload):
    """A private key cannot verify; contradictory evidence is not reported."""
    return private_key.verify(signature, payload)


def verify_unknown_receiver(key, signature, payload):
    return key.verify(signature, payload)
