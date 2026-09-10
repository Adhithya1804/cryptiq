"""Golden fixture: Ed25519 key generation, signing and verification."""

from cryptography.hazmat.primitives.asymmetric import ed25519
from cryptography.hazmat.primitives.asymmetric import ed25519 as e
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)


def generate_from_module():
    return ed25519.Ed25519PrivateKey.generate()


def generate_from_aliased_module():
    return e.Ed25519PrivateKey.generate()


def generate_from_imported_class():
    return Ed25519PrivateKey.generate()


def sign_with_annotation(private_key: Ed25519PrivateKey, payload):
    return private_key.sign(payload)


def sign_with_dotted_annotation(private_key: ed25519.Ed25519PrivateKey, payload):
    return private_key.sign(payload)


def sign_with_generated_key(payload):
    private_key = Ed25519PrivateKey.generate()
    return private_key.sign(payload)


def verify_with_annotation(public_key: Ed25519PublicKey, signature, payload):
    return public_key.verify(signature, payload)


def verify_with_derived_key(signature, payload):
    private_key = Ed25519PrivateKey.generate()
    public_key = private_key.public_key()
    return public_key.verify(signature, payload)


def load_a_key_is_not_generating_one(data):
    """from_private_bytes establishes the key but generates no key material."""
    private_key = Ed25519PrivateKey.from_private_bytes(data)
    return private_key.sign(b"x")


def sign_unknown_receiver(key, payload):
    return key.sign(payload)


def a_lookalike_class_is_not_ed25519(payload):
    class Ed25519PrivateKey:
        def sign(self, data):
            return data

    return Ed25519PrivateKey().sign(payload)
