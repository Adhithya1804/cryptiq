from __future__ import annotations

from typing import Any

from app.engine.models import (
    AnalysisContext,
    Confidence,
    CryptoRole,
    ParsedFile,
    RawObservation,
    RoleInference,
)

# Explicit digital signature APIs across supported libraries
EXPLICIT_SIGNATURE_APIS = {
    "RSAPrivateKey.sign",
    "RSAPublicKey.verify",
    "EllipticCurvePrivateKey.sign",
    "EllipticCurvePublicKey.verify",
    "Ed25519PrivateKey.sign",
    "Ed25519PublicKey.verify",
}

# Explicit key establishment APIs
EXPLICIT_KEY_ESTABLISHMENT_APIS = {
    "X25519PrivateKey.exchange",
    "ECDH.exchange",
    "RSAPrivateKey.decrypt",
    "RSAPublicKey.encrypt",
}

# Explicit symmetric cipher APIs
EXPLICIT_SYMMETRIC_APIS = {
    "algorithms.AES",
    "AES.new",
}


class RoleClassifier:
    """
    Deterministic cryptographic role classifier for Cryptiq.
    Enforces the strict role classification hierarchy:
      1. Explicit API Semantics (HIGH confidence)
      2. Known Cryptographic Object Context (MEDIUM confidence)
      3. Call-site Context (LOW confidence)
      4. UNKNOWN Fallback (LOW confidence)
    Never infers role from algorithm name alone; treats dual-use and ambiguous operations as UNKNOWN.
    """

    def classify(
        self,
        raw_observation: RawObservation,
        parsed_file: ParsedFile | AnalysisContext | None = None,
    ) -> RoleInference:
        """
        Classify a raw observation into an inferred cryptographic role with confidence.
        """
        if not raw_observation or not isinstance(raw_observation, RawObservation):
            return RoleInference(
                role=CryptoRole.UNKNOWN,
                confidence=Confidence.LOW,
                reasoning="Malformed or missing raw observation",
                hierarchy_level="UNKNOWN",
            )

        api = getattr(raw_observation, "api", "") or ""
        operation = getattr(raw_observation, "operation", "") or ""
        algorithm = getattr(raw_observation, "algorithm", "") or ""
        metadata = getattr(raw_observation, "metadata", {}) or {}

        # -----------------------------------------------------------------
        # Level 1: Explicit API Semantics (Confidence: HIGH)
        # -----------------------------------------------------------------
        level1_match = self._classify_explicit_api(api, operation, algorithm, metadata)
        if level1_match is not None:
            return level1_match

        # -----------------------------------------------------------------
        # Level 2: Known Cryptographic Object Context (Confidence: MEDIUM)
        # -----------------------------------------------------------------
        level2_match = self._classify_object_context(api, operation, algorithm, metadata, parsed_file)
        if level2_match is not None:
            return level2_match

        # -----------------------------------------------------------------
        # Level 3: Call-site Context (Confidence: LOW)
        # -----------------------------------------------------------------
        level3_match = self._classify_callsite_context(api, operation, metadata, parsed_file)
        if level3_match is not None:
            return level3_match

        # -----------------------------------------------------------------
        # Level 4: UNKNOWN Fallback (Confidence: LOW)
        # -----------------------------------------------------------------
        return RoleInference(
            role=CryptoRole.UNKNOWN,
            confidence=Confidence.LOW,
            reasoning=f"Ambiguous cryptographic operation '{operation}' on API '{api}' without conclusive context",
            hierarchy_level="UNKNOWN",
        )

    def _classify_explicit_api(
        self,
        api: str,
        operation: str,
        algorithm: str,
        metadata: dict[str, Any],
    ) -> RoleInference | None:
        """
        Tier 1: Check explicit cryptographic API method names and exact operations.
        """
        # 1. Digital Signature: explicit sign/verify operations on asymmetric key classes
        if operation in ("SIGN", "VERIFY") and (api in EXPLICIT_SIGNATURE_APIS or algorithm in ("ECDSA", "Ed25519", "RSA")):
            # Distinguish from generic .sign()
            if api in EXPLICIT_SIGNATURE_APIS or any(k in api for k in ("PrivateKey.sign", "PublicKey.verify", "ec.ECDSA")):
                return RoleInference(
                    role=CryptoRole.DIGITAL_SIGNATURE,
                    confidence=Confidence.HIGH,
                    reasoning=f"Explicit digital signature API semantics ({api})",
                    hierarchy_level="EXPLICIT_API",
                )

        # 2. Key Establishment: explicit key exchange or asymmetric key transport
        if operation in ("KEY_EXCHANGE", "EXCHANGE") and (api in EXPLICIT_KEY_ESTABLISHMENT_APIS or "exchange" in api):
            if api in EXPLICIT_KEY_ESTABLISHMENT_APIS or any(k in api for k in ("X25519", "ECDH")):
                return RoleInference(
                    role=CryptoRole.KEY_ESTABLISHMENT,
                    confidence=Confidence.HIGH,
                    reasoning=f"Explicit key agreement API semantics ({api})",
                    hierarchy_level="EXPLICIT_API",
                )

        # Dedicated key exchange key generation (e.g. X25519PrivateKey.generate)
        if operation == "KEYGEN" and algorithm in ("X25519", "ECDH"):
            return RoleInference(
                role=CryptoRole.KEY_ESTABLISHMENT,
                confidence=Confidence.HIGH,
                reasoning=f"Dedicated key agreement key generation ({api})",
                hierarchy_level="EXPLICIT_API",
            )

        # Dedicated signature key generation (e.g. Ed25519PrivateKey.generate)
        if operation == "KEYGEN" and algorithm in ("Ed25519", "ECDSA"):
            return RoleInference(
                role=CryptoRole.DIGITAL_SIGNATURE,
                confidence=Confidence.HIGH,
                reasoning=f"Dedicated digital signature key generation ({api})",
                hierarchy_level="EXPLICIT_API",
            )

        # Asymmetric encryption/decryption on RSA (used for key transport in PQC mapping)
        if algorithm == "RSA" and operation in ("ENCRYPT", "DECRYPT"):
            if api in ("RSAPublicKey.encrypt", "RSAPrivateKey.decrypt"):
                return RoleInference(
                    role=CryptoRole.KEY_ESTABLISHMENT,
                    confidence=Confidence.HIGH,
                    reasoning=f"Explicit asymmetric key transport/encryption semantics ({api})",
                    hierarchy_level="EXPLICIT_API",
                )

        # 3. Symmetric Encryption: AES operations
        if operation == "SYMMETRIC_ENCRYPTION" or api in EXPLICIT_SYMMETRIC_APIS or (algorithm == "AES" and "AES" in api):
            return RoleInference(
                role=CryptoRole.SYMMETRIC_ENCRYPTION,
                confidence=Confidence.HIGH,
                reasoning=f"Explicit symmetric cipher API semantics ({api})",
                hierarchy_level="EXPLICIT_API",
            )

        # 4. Hash Functions
        if operation == "HASH" or api.startswith("hashes.") or api.startswith("hashlib."):
            return RoleInference(
                role=CryptoRole.HASH,
                confidence=Confidence.HIGH,
                reasoning=f"Explicit cryptographic hash API semantics ({api})",
                hierarchy_level="EXPLICIT_API",
            )

        # 5. Protocol
        if operation == "PROTOCOL":
            return RoleInference(
                role=CryptoRole.PROTOCOL,
                confidence=Confidence.HIGH,
                reasoning=f"Explicit cryptographic protocol API semantics ({api})",
                hierarchy_level="EXPLICIT_API",
            )

        return None

    def _classify_object_context(
        self,
        api: str,
        operation: str,
        algorithm: str,
        metadata: dict[str, Any],
        parsed_file: ParsedFile | AnalysisContext | None,
    ) -> RoleInference | None:
        """
        Tier 2: Inspect receiver object context from the symbol table or metadata.
        """
        receiver_name = metadata.get("receiver_name") or (api.split(".")[0] if "." in api else "")
        if not receiver_name or not parsed_file:
            return None

        symbols = getattr(parsed_file, "symbols", None) or getattr(parsed_file, "symbol_table", None)
        if not symbols or not isinstance(symbols, dict):
            return None

        symbol_info = symbols.get(receiver_name)
        if not symbol_info:
            return None

        symbol_str = str(symbol_info)
        if "RSAPrivateKey" in symbol_str or "EllipticCurvePrivateKey" in symbol_str or "Ed25519PrivateKey" in symbol_str:
            if operation in ("SIGN", "VERIFY"):
                return RoleInference(
                    role=CryptoRole.DIGITAL_SIGNATURE,
                    confidence=Confidence.MEDIUM,
                    reasoning=f"Receiver '{receiver_name}' resolves to signature key object in symbol table",
                    hierarchy_level="OBJECT_CONTEXT",
                )
        elif "X25519" in symbol_str or "ECDH" in symbol_str:
            if operation in ("KEY_EXCHANGE", "EXCHANGE"):
                return RoleInference(
                    role=CryptoRole.KEY_ESTABLISHMENT,
                    confidence=Confidence.MEDIUM,
                    reasoning=f"Receiver '{receiver_name}' resolves to key agreement object in symbol table",
                    hierarchy_level="OBJECT_CONTEXT",
                )
        elif "AES" in symbol_str or "Cipher" in symbol_str:
            return RoleInference(
                role=CryptoRole.SYMMETRIC_ENCRYPTION,
                confidence=Confidence.MEDIUM,
                reasoning=f"Receiver '{receiver_name}' resolves to cipher object in symbol table",
                hierarchy_level="OBJECT_CONTEXT",
            )

        return None

    def _classify_callsite_context(
        self,
        api: str,
        operation: str,
        metadata: dict[str, Any],
        parsed_file: ParsedFile | AnalysisContext | None,
    ) -> RoleInference | None:
        """
        Tier 3: Inspect surrounding function or method name for call-site clues.
        """
        func_name = (metadata.get("enclosing_function") or "").lower()
        if not func_name:
            return None

        if any(term in func_name for term in ("sign", "auth", "attest", "cert")):
            return RoleInference(
                role=CryptoRole.DIGITAL_SIGNATURE,
                confidence=Confidence.LOW,
                reasoning=f"Enclosing function '{func_name}' suggests digital signature call-site context",
                hierarchy_level="CALL_SITE_CONTEXT",
            )

        if any(term in func_name for term in ("handshake", "exchange", "kex", "dh", "agree")):
            return RoleInference(
                role=CryptoRole.KEY_ESTABLISHMENT,
                confidence=Confidence.LOW,
                reasoning=f"Enclosing function '{func_name}' suggests key agreement call-site context",
                hierarchy_level="CALL_SITE_CONTEXT",
            )

        if any(term in func_name for term in ("encrypt", "decrypt", "cipher")):
            return RoleInference(
                role=CryptoRole.SYMMETRIC_ENCRYPTION,
                confidence=Confidence.LOW,
                reasoning=f"Enclosing function '{func_name}' suggests symmetric encryption call-site context",
                hierarchy_level="CALL_SITE_CONTEXT",
            )

        return None
