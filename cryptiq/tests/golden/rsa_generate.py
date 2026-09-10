"""Golden fixture: RSA key generation, in every import form the rule supports."""

import cryptography.hazmat.primitives.asymmetric.rsa
import cryptography.hazmat.primitives.asymmetric.rsa as rsa_aliased
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.asymmetric.rsa import generate_private_key


def from_module_import():
    return rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
    )


def from_aliased_module_import():
    return rsa_aliased.generate_private_key(public_exponent=65537, key_size=2048)


def from_fully_qualified_import():
    return cryptography.hazmat.primitives.asymmetric.rsa.generate_private_key(
        public_exponent=65537, key_size=2048
    )


def from_direct_function_import():
    return generate_private_key(public_exponent=65537, key_size=2048)


def not_rsa(parameters, my_rsa):
    """Nothing here is RSA, whatever the names say."""
    parameters.generate_private_key()
    my_rsa.generate_private_key()
    print("RSA")
    label = "cryptography.hazmat.primitives.asymmetric.rsa"
    return label
