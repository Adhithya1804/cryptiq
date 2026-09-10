"""Expected observations for the Phase 7 golden fixtures.

Each entry is (start_line, rule_id, algorithm, api, operation, confidence,
evidence_basis, enclosing_function). The fixtures also contain negative cases;
anything absent from these tables must produce no observation at all.

Hash observations appear inside the ECDSA fixtures because the signature calls
genuinely name SHA-256. Two rules reporting two different calls on one line is
not a contradiction: each records what its own call node shows.
"""

EXPECTED: dict[str, tuple[tuple, ...]] = {
    "ecdsa_sign.py": (
        (9, "PY-CRYPTO-ECDSA", "ECDSA", "ECDSA.sign", "SIGN", "HIGH", "DIRECT_MODULE_API", 'sign_with_direct_marker'),
        (9, "PY-CRYPTO-HASH", "SHA-256", "hashes.SHA256", "HASH", "HIGH", "DIRECT_MODULE_API", 'sign_with_direct_marker'),
        (13, "PY-CRYPTO-ECDSA", "ECDSA", "ECDSA.sign", "SIGN", "HIGH", "DIRECT_MODULE_API", 'sign_with_aliased_module'),
        (13, "PY-CRYPTO-HASH", "SHA-256", "hashes.SHA256", "HASH", "HIGH", "DIRECT_MODULE_API", 'sign_with_aliased_module'),
        (17, "PY-CRYPTO-HASH", "SHA-256", "hashes.SHA256", "HASH", "HIGH", "DIRECT_MODULE_API", 'sign_with_assigned_marker'),
        (18, "PY-CRYPTO-ECDSA", "ECDSA", "ECDSA.sign", "SIGN", "MEDIUM", "CONSTRUCTOR_ASSIGNMENT", 'sign_with_assigned_marker'),
        (23, "PY-CRYPTO-ECDSA", "ECDSA", "ECDSA.sign", "SIGN", "HIGH", "DIRECT_MODULE_API", 'sign_on_a_chained_receiver'),
        (23, "PY-CRYPTO-HASH", "SHA-256", "hashes.SHA256", "HASH", "HIGH", "DIRECT_MODULE_API", 'sign_on_a_chained_receiver'),
    ),
    "ecdsa_verify.py": (
        (8, "PY-CRYPTO-ECDSA", "ECDSA", "ECDSA.verify", "VERIFY", "HIGH", "DIRECT_MODULE_API", 'verify_with_imported_marker'),
        (8, "PY-CRYPTO-HASH", "SHA-256", "hashes.SHA256", "HASH", "HIGH", "DIRECT_MODULE_API", 'verify_with_imported_marker'),
        (12, "PY-CRYPTO-HASH", "SHA-256", "hashes.SHA256", "HASH", "HIGH", "DIRECT_MODULE_API", 'verify_with_assigned_marker'),
        (13, "PY-CRYPTO-ECDSA", "ECDSA", "ECDSA.verify", "VERIFY", "MEDIUM", "CONSTRUCTOR_ASSIGNMENT", 'verify_with_assigned_marker'),
        (18, "PY-CRYPTO-HASH", "SHA-256", "hashes.SHA256", "HASH", "HIGH", "DIRECT_MODULE_API", 'verify_with_an_ambiguous_marker'),
    ),
    "ed25519.py": (
        (12, "PY-CRYPTO-ED25519", "Ed25519", "Ed25519PrivateKey.generate", "KEY_GENERATION", "HIGH", "DIRECT_MODULE_API", 'generate_from_module'),
        (16, "PY-CRYPTO-ED25519", "Ed25519", "Ed25519PrivateKey.generate", "KEY_GENERATION", "HIGH", "DIRECT_MODULE_API", 'generate_from_aliased_module'),
        (20, "PY-CRYPTO-ED25519", "Ed25519", "Ed25519PrivateKey.generate", "KEY_GENERATION", "HIGH", "DIRECT_MODULE_API", 'generate_from_imported_class'),
        (24, "PY-CRYPTO-ED25519", "Ed25519", "Ed25519PrivateKey.sign", "SIGN", "HIGH", "CLASS_ANNOTATION", 'sign_with_annotation'),
        (28, "PY-CRYPTO-ED25519", "Ed25519", "Ed25519PrivateKey.sign", "SIGN", "HIGH", "CLASS_ANNOTATION", 'sign_with_dotted_annotation'),
        (32, "PY-CRYPTO-ED25519", "Ed25519", "Ed25519PrivateKey.generate", "KEY_GENERATION", "HIGH", "DIRECT_MODULE_API", 'sign_with_generated_key'),
        (33, "PY-CRYPTO-ED25519", "Ed25519", "Ed25519PrivateKey.sign", "SIGN", "MEDIUM", "CONSTRUCTOR_ASSIGNMENT", 'sign_with_generated_key'),
        (37, "PY-CRYPTO-ED25519", "Ed25519", "Ed25519PublicKey.verify", "VERIFY", "HIGH", "CLASS_ANNOTATION", 'verify_with_annotation'),
        (41, "PY-CRYPTO-ED25519", "Ed25519", "Ed25519PrivateKey.generate", "KEY_GENERATION", "HIGH", "DIRECT_MODULE_API", 'verify_with_derived_key'),
        (43, "PY-CRYPTO-ED25519", "Ed25519", "Ed25519PublicKey.verify", "VERIFY", "MEDIUM", "CONSTRUCTOR_ASSIGNMENT", 'verify_with_derived_key'),
        (49, "PY-CRYPTO-ED25519", "Ed25519", "Ed25519PrivateKey.sign", "SIGN", "MEDIUM", "CONSTRUCTOR_ASSIGNMENT", 'load_a_key_is_not_generating_one'),
    ),
    "ecdh.py": (
        (8, "PY-CRYPTO-ECDH", "ECDH", "ECDH.exchange", "KEY_ESTABLISHMENT", "HIGH", "DIRECT_MODULE_API", 'exchange_with_direct_marker'),
        (12, "PY-CRYPTO-ECDH", "ECDH", "ECDH.exchange", "KEY_ESTABLISHMENT", "HIGH", "DIRECT_MODULE_API", 'exchange_with_imported_marker'),
        (17, "PY-CRYPTO-ECDH", "ECDH", "ECDH.exchange", "KEY_ESTABLISHMENT", "MEDIUM", "CONSTRUCTOR_ASSIGNMENT", 'exchange_with_assigned_marker'),
        (23, "PY-CRYPTO-ECDSA", "ECDSA", "ECDSA.sign", "SIGN", "HIGH", "DIRECT_MODULE_API", 'sign_is_not_key_agreement'),
        (23, "PY-CRYPTO-HASH", "SHA-256", "hashes.SHA256", "HASH", "HIGH", "DIRECT_MODULE_API", 'sign_is_not_key_agreement'),
    ),
    "x25519.py": (
        (12, "PY-CRYPTO-X25519", "X25519", "X25519PrivateKey.generate", "KEY_GENERATION", "HIGH", "DIRECT_MODULE_API", 'generate_from_module'),
        (16, "PY-CRYPTO-X25519", "X25519", "X25519PrivateKey.generate", "KEY_GENERATION", "HIGH", "DIRECT_MODULE_API", 'generate_from_aliased_module'),
        (20, "PY-CRYPTO-X25519", "X25519", "X25519PrivateKey.exchange", "KEY_ESTABLISHMENT", "HIGH", "CLASS_ANNOTATION", 'exchange_with_annotation'),
        (24, "PY-CRYPTO-X25519", "X25519", "X25519PrivateKey.generate", "KEY_GENERATION", "HIGH", "DIRECT_MODULE_API", 'exchange_with_generated_key'),
        (25, "PY-CRYPTO-X25519", "X25519", "X25519PrivateKey.exchange", "KEY_ESTABLISHMENT", "MEDIUM", "CONSTRUCTOR_ASSIGNMENT", 'exchange_with_generated_key'),
    ),
    "aes.py": (
        (9, "PY-CRYPTO-AES", "AES", "algorithms.AES", "CONSTRUCTION", "HIGH", "DIRECT_MODULE_API", 'construct_the_algorithm'),
        (13, "PY-CRYPTO-AES", "AES", "algorithms.AES", "CONSTRUCTION", "HIGH", "DIRECT_MODULE_API", 'encrypt_through_a_cipher'),
        (14, "PY-CRYPTO-AES", "AES", "Cipher.encryptor", "ENCRYPT", "MEDIUM", "CONSTRUCTOR_ASSIGNMENT", 'encrypt_through_a_cipher'),
        (19, "PY-CRYPTO-AES", "AES", "algorithms.AES", "CONSTRUCTION", "HIGH", "DIRECT_MODULE_API", 'decrypt_through_a_cipher'),
        (20, "PY-CRYPTO-AES", "AES", "Cipher.decryptor", "DECRYPT", "MEDIUM", "CONSTRUCTOR_ASSIGNMENT", 'decrypt_through_a_cipher'),
        (25, "PY-CRYPTO-AES", "AES", "aead.AESGCM", "CONSTRUCTION", "HIGH", "DIRECT_MODULE_API", 'encrypt_with_an_aead'),
        (26, "PY-CRYPTO-AES", "AES", "AESAEAD.encrypt", "ENCRYPT", "MEDIUM", "CONSTRUCTOR_ASSIGNMENT", 'encrypt_with_an_aead'),
        (30, "PY-CRYPTO-AES", "AES", "aead.AESGCM", "CONSTRUCTION", "HIGH", "DIRECT_MODULE_API", 'decrypt_with_an_aliased_aead'),
        (31, "PY-CRYPTO-AES", "AES", "AESAEAD.decrypt", "DECRYPT", "MEDIUM", "CONSTRUCTOR_ASSIGNMENT", 'decrypt_with_an_aliased_aead'),
    ),
    "hashes.py": (
        (9, "PY-CRYPTO-HASH", "SHA-256", "hashes.SHA256", "HASH", "HIGH", "DIRECT_MODULE_API", 'modern_hashes'),
        (9, "PY-CRYPTO-HASH", "SHA-384", "hashes.SHA384", "HASH", "HIGH", "DIRECT_MODULE_API", 'modern_hashes'),
        (9, "PY-CRYPTO-HASH", "SHA-512", "hashes.SHA512", "HASH", "HIGH", "DIRECT_MODULE_API", 'modern_hashes'),
        (14, "PY-CRYPTO-HASH", "SHA-1", "hashes.SHA1", "HASH", "HIGH", "DIRECT_MODULE_API", 'legacy_hashes'),
        (14, "PY-CRYPTO-HASH", "MD5", "hashes.MD5", "HASH", "HIGH", "DIRECT_MODULE_API", 'legacy_hashes'),
        (18, "PY-CRYPTO-HASH", "SHA3-256", "hashes.SHA3_256", "HASH", "HIGH", "DIRECT_MODULE_API", 'sha3_family'),
        (18, "PY-CRYPTO-HASH", "SHA3-512", "hashes.SHA3_512", "HASH", "HIGH", "DIRECT_MODULE_API", 'sha3_family'),
        (22, "PY-CRYPTO-HASH", "BLAKE2b", "hashes.BLAKE2b", "HASH", "HIGH", "DIRECT_MODULE_API", 'blake_family'),
        (22, "PY-CRYPTO-HASH", "BLAKE2s", "hashes.BLAKE2s", "HASH", "HIGH", "DIRECT_MODULE_API", 'blake_family'),
        (26, "PY-CRYPTO-HASH", "SHA-256", "hashes.SHA256", "HASH", "HIGH", "DIRECT_MODULE_API", 'aliased_module'),
        (30, "PY-CRYPTO-HASH", "SHA-256", "hashes.SHA256", "HASH", "HIGH", "DIRECT_MODULE_API", 'imported_class'),
        (34, "PY-CRYPTO-HASH", "SHA-256", "hashes.SHA256", "HASH", "HIGH", "DIRECT_MODULE_API", 'used_inside_a_digest'),
    ),
}
