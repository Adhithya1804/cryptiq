"""Expected observations for the golden fixtures.

Each entry is (start_line, api, operation, confidence, evidence_basis,
enclosing_function, enclosing_class). The fixtures also contain negative cases;
anything absent from these tables must produce no observation at all.
"""

EXPECTED: dict[str, tuple[tuple, ...]] = {
    "rsa_generate.py": (
        (10, "rsa.generate_private_key", "KEY_GENERATION", "HIGH", "DIRECT_MODULE_API",
         "from_module_import", None),
        (17, "rsa.generate_private_key", "KEY_GENERATION", "HIGH", "DIRECT_MODULE_API",
         "from_aliased_module_import", None),
        (21, "rsa.generate_private_key", "KEY_GENERATION", "HIGH", "DIRECT_MODULE_API",
         "from_fully_qualified_import", None),
        (27, "rsa.generate_private_key", "KEY_GENERATION", "HIGH", "DIRECT_MODULE_API",
         "from_direct_function_import", None),
    ),
    "rsa_sign.py": (
        (9, "RSAPrivateKey.sign", "SIGN", "HIGH", "CLASS_ANNOTATION",
         "sign_with_annotation", None),
        (13, "RSAPrivateKey.sign", "SIGN", "HIGH", "CLASS_ANNOTATION",
         "sign_with_aliased_annotation", None),
        (17, "RSAPrivateKey.sign", "SIGN", "HIGH", "CLASS_ANNOTATION",
         "sign_with_dotted_annotation", None),
        (21, "rsa.generate_private_key", "KEY_GENERATION", "HIGH", "DIRECT_MODULE_API",
         "sign_with_assigned_key", None),
        (22, "RSAPrivateKey.sign", "SIGN", "MEDIUM", "CONSTRUCTOR_ASSIGNMENT",
         "sign_with_assigned_key", None),
        (35, "RSAPrivateKey.sign", "SIGN", "HIGH", "CLASS_ANNOTATION",
         "sign_with_annotated_variable", None),
        (45, "rsa.generate_private_key", "KEY_GENERATION", "HIGH", "DIRECT_MODULE_API",
         "sign_reassigned", None),
        (54, "RSAPrivateKey.sign", "SIGN", "MEDIUM", "ESTABLISHED_ALIAS",
         "sign_with_aliased_key", None),
    ),
    "rsa_verify.py": (
        (8, "RSAPublicKey.verify", "VERIFY", "HIGH", "CLASS_ANNOTATION",
         "verify_with_annotation", None),
        (12, "rsa.generate_private_key", "KEY_GENERATION", "HIGH", "DIRECT_MODULE_API",
         "verify_with_derived_key", None),
        (14, "RSAPublicKey.verify", "VERIFY", "MEDIUM", "CONSTRUCTOR_ASSIGNMENT",
         "verify_with_derived_key", None),
    ),
    "rsa_encrypt.py": (
        (8, "RSAPublicKey.encrypt", "ENCRYPT", "HIGH", "CLASS_ANNOTATION",
         "encrypt_with_annotation", None),
        (13, "rsa.generate_private_key", "KEY_GENERATION", "HIGH", "DIRECT_MODULE_API",
         "encrypt_on_a_chained_call", None),
        (18, "rsa.generate_private_key", "KEY_GENERATION", "HIGH", "DIRECT_MODULE_API",
         "encrypt_with_assigned_derived_key", None),
        (20, "RSAPublicKey.encrypt", "ENCRYPT", "MEDIUM", "CONSTRUCTOR_ASSIGNMENT",
         "encrypt_with_assigned_derived_key", None),
    ),
    "rsa_decrypt.py": (
        (8, "RSAPrivateKey.decrypt", "DECRYPT", "HIGH", "CLASS_ANNOTATION",
         "decrypt_with_annotation", None),
        (12, "rsa.generate_private_key", "KEY_GENERATION", "HIGH", "DIRECT_MODULE_API",
         "decrypt_with_assigned_key", None),
        (13, "RSAPrivateKey.decrypt", "DECRYPT", "MEDIUM", "CONSTRUCTOR_ASSIGNMENT",
         "decrypt_with_assigned_key", None),
        (20, "RSAPrivateKey.decrypt", "DECRYPT", "HIGH", "CLASS_ANNOTATION",
         "Decryptor.decrypt", "Decryptor"),
    ),
}
