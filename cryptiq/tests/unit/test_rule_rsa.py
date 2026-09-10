"""RSA detection from Python syntax, positive and negative."""

import pytest

from app.engine.parser import PythonParser
from app.engine.rules import (
    CryptoOperation,
    EvidenceBasis,
    MatchConfidence,
    RsaRule,
    evaluate_file,
    evaluate_files,
)

FROM_IMPORT = "from cryptography.hazmat.primitives.asymmetric import rsa\n"
CLASS_IMPORT = "from cryptography.hazmat.primitives.asymmetric.rsa import RSAPrivateKey\n"
PUBLIC_CLASS_IMPORT = "from cryptography.hazmat.primitives.asymmetric.rsa import RSAPublicKey\n"


def matches(source: str, path: str = "src/keys.py"):
    return evaluate_file(PythonParser().parse(source, path))


def single(source: str, path: str = "src/keys.py"):
    found = matches(source, path)
    assert len(found) == 1, [match.api for match in found]
    return found[0]


def test_direct_module_api_is_high_confidence() -> None:
    match = single(FROM_IMPORT + "key = rsa.generate_private_key()\n")

    assert match.rule_id == "PY-CRYPTO-RSA"
    assert match.api == "rsa.generate_private_key"
    assert match.operation is CryptoOperation.KEY_GENERATION
    assert match.confidence is MatchConfidence.HIGH
    assert match.evidence_basis is EvidenceBasis.DIRECT_MODULE_API


def test_an_aliased_module_import_resolves() -> None:
    source = (
        "import cryptography.hazmat.primitives.asymmetric.rsa as crypto_rsa\n"
        "key = crypto_rsa.generate_private_key()\n"
    )

    assert single(source).api == "rsa.generate_private_key"


def test_a_fully_qualified_import_resolves() -> None:
    source = (
        "import cryptography.hazmat.primitives.asymmetric.rsa\n"
        "key = cryptography.hazmat.primitives.asymmetric.rsa.generate_private_key()\n"
    )

    assert single(source).api == "rsa.generate_private_key"


def test_a_directly_imported_function_resolves() -> None:
    source = (
        "from cryptography.hazmat.primitives.asymmetric.rsa import generate_private_key\n"
        "key = generate_private_key()\n"
    )

    assert single(source).api == "rsa.generate_private_key"


def test_an_unbound_class_method_call_is_a_class_import_match() -> None:
    source = CLASS_IMPORT + "RSAPrivateKey.sign(key, payload)\n"

    match = single(source)
    assert match.api == "RSAPrivateKey.sign"
    assert match.evidence_basis is EvidenceBasis.CLASS_IMPORT
    assert match.confidence is MatchConfidence.HIGH


def test_an_explicit_class_annotation_establishes_the_receiver() -> None:
    source = CLASS_IMPORT + "def sign(key: RSAPrivateKey, payload):\n    return key.sign(payload)\n"

    match = single(source)
    assert match.api == "RSAPrivateKey.sign"
    assert match.operation is CryptoOperation.SIGN
    assert match.confidence is MatchConfidence.HIGH
    assert match.evidence_basis is EvidenceBasis.CLASS_ANNOTATION
    assert match.enclosing_function == "sign"


def test_an_aliased_class_annotation_establishes_the_receiver() -> None:
    source = (
        "from cryptography.hazmat.primitives.asymmetric.rsa import RSAPrivateKey as Key\n"
        "def sign(key: Key, payload):\n"
        "    return key.sign(payload)\n"
    )

    assert single(source).api == "RSAPrivateKey.sign"


def test_a_dotted_class_annotation_establishes_the_receiver() -> None:
    source = FROM_IMPORT + (
        "def sign(key: rsa.RSAPrivateKey, payload):\n    return key.sign(payload)\n"
    )

    assert single(source).api == "RSAPrivateKey.sign"


def test_an_annotated_local_variable_establishes_the_receiver() -> None:
    source = CLASS_IMPORT + (
        "def sign(payload):\n    key: RSAPrivateKey = load()\n    return key.sign(payload)\n"
    )

    assert single(source).api == "RSAPrivateKey.sign"


def test_an_assignment_from_the_constructor_establishes_the_receiver() -> None:
    source = FROM_IMPORT + (
        "def sign(payload):\n"
        "    key = rsa.generate_private_key()\n"
        "    return key.sign(payload)\n"
    )

    found = matches(source)
    assert [match.api for match in found] == [
        "rsa.generate_private_key",
        "RSAPrivateKey.sign",
    ]
    assert found[1].confidence is MatchConfidence.MEDIUM
    assert found[1].evidence_basis is EvidenceBasis.CONSTRUCTOR_ASSIGNMENT


def test_a_public_key_derived_from_an_established_private_key() -> None:
    source = FROM_IMPORT + (
        "def check(signature, payload):\n"
        "    key = rsa.generate_private_key()\n"
        "    public = key.public_key()\n"
        "    return public.verify(signature, payload)\n"
    )

    found = matches(source)
    assert [match.api for match in found] == [
        "rsa.generate_private_key",
        "RSAPublicKey.verify",
    ]
    assert found[1].operation is CryptoOperation.VERIFY


def test_public_key_operations_are_recognised() -> None:
    source = PUBLIC_CLASS_IMPORT + (
        "def use(key: RSAPublicKey, payload, signature):\n"
        "    key.verify(signature, payload)\n"
        "    return key.encrypt(payload, None)\n"
    )

    found = matches(source)
    assert [(match.api, match.operation.value) for match in found] == [
        ("RSAPublicKey.verify", "VERIFY"),
        ("RSAPublicKey.encrypt", "ENCRYPT"),
    ]


def test_private_key_decryption_is_recognised() -> None:
    source = CLASS_IMPORT + (
        "def open_it(key: RSAPrivateKey, ciphertext):\n    return key.decrypt(ciphertext, None)\n"
    )

    match = single(source)
    assert match.api == "RSAPrivateKey.decrypt"
    assert match.operation is CryptoOperation.DECRYPT


def test_a_multiline_call_uses_the_exact_ast_span() -> None:
    source = FROM_IMPORT + (
        "key = rsa.generate_private_key(\n"
        "    public_exponent=65537,\n"
        "    key_size=2048,\n"
        ")\n"
    )

    location = single(source).location
    assert location.start_line == 2
    assert location.end_line == 5
    assert location.start_column == 6
    assert location.end_column == 1


def test_a_nested_call_records_its_own_span_and_scope() -> None:
    source = FROM_IMPORT + (
        "class Factory:\n"
        "    def build(self):\n"
        "        return wrap(rsa.generate_private_key())\n"
    )

    match = single(source)
    assert match.enclosing_function == "Factory.build"
    assert match.enclosing_class == "Factory"
    assert match.location.start_line == 4


def test_the_enclosing_class_is_recorded_for_methods() -> None:
    source = CLASS_IMPORT + (
        "class Signer:\n"
        "    def sign(self, key: RSAPrivateKey, payload):\n"
        "        return key.sign(payload)\n"
    )

    match = single(source)
    assert match.enclosing_function == "Signer.sign"
    assert match.enclosing_class == "Signer"


def test_a_method_on_the_wrong_half_of_the_key_pair_is_not_reported() -> None:
    source = CLASS_IMPORT + (
        "def bad(key: RSAPrivateKey, signature, payload):\n"
        "    key.verify(signature, payload)\n"
        "    return key.encrypt(payload, None)\n"
    )

    assert matches(source) == []


def test_only_the_call_produces_an_observation() -> None:
    """The attribute nodes inside ``rsa.generate_private_key`` must not match."""
    source = FROM_IMPORT + "key = rsa.generate_private_key()\n"

    assert len(matches(source)) == 1


def test_repeated_calls_each_produce_their_own_observation() -> None:
    source = FROM_IMPORT + (
        "first = rsa.generate_private_key()\nsecond = rsa.generate_private_key()\n"
    )

    found = matches(source)
    assert [match.location.start_line for match in found] == [2, 3]


def test_matches_are_ordered_by_path_then_position() -> None:
    files = [
        PythonParser().parse(FROM_IMPORT + "b = rsa.generate_private_key()\n", "b.py"),
        PythonParser().parse(
            FROM_IMPORT + "a = rsa.generate_private_key()\nc = rsa.generate_private_key()\n",
            "a.py",
        ),
    ]

    found = evaluate_files(files)
    assert [(match.file_path, match.location.start_line) for match in found] == [
        ("a.py", 2),
        ("a.py", 3),
        ("b.py", 2),
    ]


def test_a_file_that_failed_to_parse_yields_nothing() -> None:
    assert matches("def broken(:\n") == []


def test_the_rule_can_be_run_on_its_own() -> None:
    parsed = PythonParser().parse(FROM_IMPORT + "key = rsa.generate_private_key()\n", "a.py")

    assert len(evaluate_file(parsed, rules=[RsaRule()])) == 1


@pytest.mark.parametrize(
    "source",
    [
        'print("RSA")\n',
        'variable = "RSA"\n',
        'label = "cryptography.hazmat.primitives.asymmetric.rsa"\n',
        "# rsa.generate_private_key is mentioned here\nvalue = 1\n",
        '"""A docstring about rsa.generate_private_key and RSAPrivateKey."""\nvalue = 1\n',
        "my_rsa = object()\nmy_rsa.sign(payload)\n",
        "rsa = object()\nrsa.generate_private_key()\n",
        "import rsa\nrsa.generate_private_key()\n",
        "some_object.encrypt(payload)\n",
        "def run(param):\n    return param.generate_private_key()\n",
        "def run(key, payload):\n    return key.sign(payload)\n",
        "def run(cipher, payload):\n    return cipher.encrypt(payload)\n",
        "def run(digest):\n    return digest.verify(b'')\n",
        "class RSAPrivateKey:\n    pass\n\nRSAPrivateKey().sign(b'')\n",
    ],
)
def test_negative_cases_produce_no_observation(source: str) -> None:
    assert matches(source) == []


def test_a_dh_parameter_generate_private_key_is_not_rsa() -> None:
    source = (
        "from cryptography.hazmat.primitives.asymmetric import dh\n"
        "def run():\n"
        "    parameters = dh.generate_parameters(generator=2, key_size=2048)\n"
        "    return parameters.generate_private_key()\n"
    )

    assert matches(source) == []


def test_a_reassigned_name_is_not_claimed() -> None:
    source = FROM_IMPORT + (
        "def sign(payload, flag):\n"
        "    key = rsa.generate_private_key()\n"
        "    if flag:\n"
        "        key = load()\n"
        "    return key.sign(payload)\n"
    )

    assert [match.api for match in matches(source)] == ["rsa.generate_private_key"]


def test_an_unannotated_parameter_does_not_inherit_a_module_binding() -> None:
    source = FROM_IMPORT + (
        "key = rsa.generate_private_key()\n"
        "def sign(key, payload):\n"
        "    return key.sign(payload)\n"
    )

    assert [match.api for match in matches(source)] == ["rsa.generate_private_key"]


def test_a_module_level_binding_reaches_a_function_that_does_not_shadow_it() -> None:
    source = FROM_IMPORT + (
        "signing_key = rsa.generate_private_key()\n"
        "def sign(payload):\n"
        "    return signing_key.sign(payload)\n"
    )

    assert [match.api for match in matches(source)] == [
        "rsa.generate_private_key",
        "RSAPrivateKey.sign",
    ]


def test_a_nested_function_sees_the_binding_of_its_parent() -> None:
    source = FROM_IMPORT + (
        "def outer(payload):\n"
        "    key = rsa.generate_private_key()\n"
        "    def inner():\n"
        "        return key.sign(payload)\n"
        "    return inner\n"
    )

    assert [match.api for match in matches(source)] == [
        "rsa.generate_private_key",
        "RSAPrivateKey.sign",
    ]


def test_a_class_attribute_is_not_visible_as_a_bare_name_in_its_methods() -> None:
    source = FROM_IMPORT + (
        "class Signer:\n"
        "    key = rsa.generate_private_key()\n"
        "    def sign(self, payload):\n"
        "        return key.sign(payload)\n"
    )

    assert [match.api for match in matches(source)] == ["rsa.generate_private_key"]


def test_an_attribute_receiver_is_not_established() -> None:
    source = CLASS_IMPORT + (
        "class Signer:\n"
        "    def __init__(self, key: RSAPrivateKey):\n"
        "        self.key = key\n"
        "    def sign(self, payload):\n"
        "        return self.key.sign(payload)\n"
    )

    assert matches(source) == []


def test_an_alias_carries_an_established_binding() -> None:
    source = CLASS_IMPORT + (
        "def sign(rsa_key: RSAPrivateKey, payload):\n"
        "    private_key = rsa_key\n"
        "    return private_key.sign(payload)\n"
    )

    match = single(source)
    assert match.api == "RSAPrivateKey.sign"
    assert match.confidence is MatchConfidence.MEDIUM
    assert match.evidence_basis is EvidenceBasis.ESTABLISHED_ALIAS


def test_an_alias_overwritten_by_an_unknown_value_is_not_claimed() -> None:
    source = CLASS_IMPORT + (
        "def sign(rsa_key: RSAPrivateKey, payload, flag):\n"
        "    private_key = rsa_key\n"
        "    if flag:\n"
        "        private_key = load()\n"
        "    return private_key.sign(payload)\n"
    )

    assert matches(source) == []


def test_an_alias_of_an_unestablished_name_is_not_claimed() -> None:
    source = "def sign(thing, payload):\n    key = thing\n    return key.sign(payload)\n"

    assert matches(source) == []


def test_an_alias_chain_does_not_extend_past_one_hop() -> None:
    """Aliases read only bindings established before them, never each other."""
    source = CLASS_IMPORT + (
        "def sign(rsa_key: RSAPrivateKey, payload):\n"
        "    first = rsa_key\n"
        "    second = first\n"
        "    return second.sign(payload)\n"
    )

    assert matches(source) == []
