"""Golden fixture: RSA signing, established by annotation and by assignment."""

from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPrivateKey
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPrivateKey as PrivateKey


def sign_with_annotation(private_key: RSAPrivateKey, payload):
    return private_key.sign(payload)


def sign_with_aliased_annotation(private_key: PrivateKey, payload):
    return private_key.sign(payload)


def sign_with_dotted_annotation(private_key: rsa.RSAPrivateKey, payload):
    return private_key.sign(payload)


def sign_with_assigned_key(payload):
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    signature = private_key.sign(
        payload,
        padding.PSS(
            mgf=padding.MGF1(hashes.SHA256()),
            salt_length=padding.PSS.MAX_LENGTH,
        ),
        hashes.SHA256(),
    )
    return signature


def sign_with_annotated_variable(payload):
    key: RSAPrivateKey = load()
    return key.sign(payload)


def sign_unknown_receiver(key, payload):
    """The receiver is never established, so this is not an RSA finding."""
    return key.sign(payload)


def sign_reassigned(payload, flag):
    """One branch is not RSA, so the name is not claimed at all."""
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    if flag:
        key = load()
    return key.sign(payload)


def sign_with_aliased_key(rsa_key: RSAPrivateKey, payload):
    """An alias carries an established binding to another name."""
    private_key = rsa_key
    return private_key.sign(payload)


def sign_with_ambiguous_alias(rsa_key: RSAPrivateKey, payload, flag):
    """The alias is overwritten by something unknown, so nothing is claimed."""
    private_key = rsa_key
    if flag:
        private_key = load()
    return private_key.sign(payload)
