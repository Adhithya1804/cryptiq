"""Golden fixture: RSA decryption on an established private key."""

from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPrivateKey


def decrypt_with_annotation(private_key: RSAPrivateKey, ciphertext):
    return private_key.decrypt(ciphertext, padding.OAEP())


def decrypt_with_assigned_key(ciphertext):
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return private_key.decrypt(ciphertext, padding.OAEP())


class Decryptor:
    """Methods keep their enclosing class in the observation."""

    def decrypt(self, private_key: RSAPrivateKey, ciphertext):
        return private_key.decrypt(ciphertext, padding.OAEP())


def decrypt_unknown_receiver(key, ciphertext):
    return key.decrypt(ciphertext)
