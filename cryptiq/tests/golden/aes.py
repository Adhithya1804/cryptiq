"""Golden fixture: AES construction, encryption and decryption."""

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.ciphers.aead import AESGCM as GCM


def construct_the_algorithm(key):
    return algorithms.AES(key)


def encrypt_through_a_cipher(key, iv, payload):
    cipher = Cipher(algorithms.AES(key), modes.CBC(iv))
    encryptor = cipher.encryptor()
    return encryptor.update(payload) + encryptor.finalize()


def decrypt_through_a_cipher(key, iv, ciphertext):
    cipher = Cipher(algorithms.AES(key), modes.CBC(iv))
    decryptor = cipher.decryptor()
    return decryptor.update(ciphertext) + decryptor.finalize()


def encrypt_with_an_aead(key, nonce, payload):
    aesgcm = AESGCM(key)
    return aesgcm.encrypt(nonce, payload, None)


def decrypt_with_an_aliased_aead(key, nonce, ciphertext):
    aesgcm = GCM(key)
    return aesgcm.decrypt(nonce, ciphertext, None)


def a_cipher_built_from_another_algorithm(key, nonce, payload):
    """ChaCha20 is not AES; only the Cipher's algorithm decides."""
    cipher = Cipher(algorithms.ChaCha20(key, nonce), None)
    encryptor = cipher.encryptor()
    return encryptor.update(payload)


def a_variable_named_aes(payload):
    AES = object()
    return AES, payload


def a_generic_encrypt(box, payload):
    return box.encrypt(payload)


def a_string_mentioning_aes():
    # AES-256-GCM appears in this comment only.
    return "algorithms.AES"
