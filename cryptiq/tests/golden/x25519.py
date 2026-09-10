"""Golden fixture: X25519 key generation and key agreement."""

import cryptography.hazmat.primitives.asymmetric.x25519 as x
from cryptography.hazmat.primitives.asymmetric import x25519
from cryptography.hazmat.primitives.asymmetric.x25519 import (
    X25519PrivateKey,
    X25519PublicKey,
)


def generate_from_module():
    return x25519.X25519PrivateKey.generate()


def generate_from_aliased_module():
    return x.X25519PrivateKey.generate()


def exchange_with_annotation(private_key: X25519PrivateKey, peer_public_key):
    return private_key.exchange(peer_public_key)


def exchange_with_generated_key(peer_public_key):
    private_key = X25519PrivateKey.generate()
    return private_key.exchange(peer_public_key)


def a_public_key_does_not_exchange(public_key: X25519PublicKey, peer):
    """Only the private half performs the agreement."""
    return public_key.exchange(peer)


def a_generic_exchange_is_not_x25519(session, peer):
    return session.exchange(peer)


def an_unrelated_parameter_exchange(order_book, peer):
    return order_book.exchange(peer)
