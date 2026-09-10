"""Golden fixture: elliptic-curve key agreement, proved by the ec.ECDH marker."""

from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.ec import ECDH


def exchange_with_direct_marker(private_key, peer_public_key):
    return private_key.exchange(ec.ECDH(), peer_public_key)


def exchange_with_imported_marker(private_key, peer_public_key):
    return private_key.exchange(ECDH(), peer_public_key)


def exchange_with_assigned_marker(private_key, peer_public_key):
    algorithm = ec.ECDH()
    return private_key.exchange(algorithm, peer_public_key)


def sign_is_not_key_agreement(private_key, payload):
    from cryptography.hazmat.primitives import hashes

    return private_key.sign(payload, ec.ECDSA(hashes.SHA256()))


def a_curve_alone_is_not_key_agreement():
    return ec.SECP384R1()


def a_generic_exchange_is_not_ecdh(session, peer):
    return session.exchange(peer)
