"""Static context extraction for cryptographic findings.

Operates strictly on source text, AST context, file paths and surrounding symbols.
NEVER imports, executes, or evaluates target repository code.
"""

from __future__ import annotations

import re
from pathlib import Path

from app.engine.context.models import ContextualRole, ExtractedContext

CONTENT_ADDRESSING_CLUES = frozenset(
    {
        "tile",
        "tiles",
        "cache",
        "cache_key",
        "dedup",
        "deduplicate",
        "content",
        "content_address",
        "content_hash",
        "etag",
        "chunk",
        "fingerprint",
        "object_id",
        "storage",
        "memo",
        "memoize",
        "asset",
        "media",
    }
)

DATA_INTEGRITY_CLUES = frozenset(
    {
        "checksum",
        "integrity",
        "verify_checksum",
        "file_hash",
        "sha256sum",
        "md5sum",
        "payload_hash",
        "tamper",
    }
)

FIRMWARE_SIGNING_CLUES = frozenset(
    {
        "firmware",
        "firmware_update",
        "ota",
        "bootloader",
        "boot",
        "manifest",
        "release",
        "package_sign",
        "authenticity",
        "secure_boot",
    }
)

KEY_ESTABLISHMENT_CLUES = frozenset(
    {
        "handshake",
        "exchange",
        "session",
        "shared_secret",
        "ecdh",
        "x25519",
        "ephemeral",
        "peer",
        "negotiate",
        "key_agreement",
        "transport",
    }
)

PASSWORD_CLUES = frozenset(
    {
        "password",
        "passwd",
        "credential",
        "kdf",
        "pbkdf2",
        "salt",
        "hash_pw",
        "user_pass",
    }
)

TOKEN_RE = re.compile(r"[a-zA-Z_][a-zA-Z0-9_]*")


def _tokenize(text: str) -> set[str]:
    """Extract lowercased identifier tokens, splitting snake_case and camelCase."""
    raw_tokens = TOKEN_RE.findall(text)
    tokens: set[str] = set()
    for token in raw_tokens:
        tokens.add(token.lower())
        # Split snake_case
        for part in token.split("_"):
            if part:
                tokens.add(part.lower())
        # Split camelCase
        camel_parts = re.findall(r"[A-Z]?[a-z]+|[A-Z]+(?=[A-Z][a-z]|\b)", token)
        for part in camel_parts:
            tokens.add(part.lower())
    return tokens


def extract_context(
    *,
    finding_fingerprint: str,
    file_path: str,
    enclosing_function: str | None = None,
    enclosing_class: str | None = None,
    module_name: str | None = None,
    source_excerpt: str = "",
    root_path: Path | None = None,
    start_line: int | None = None,
    deterministic_role: str = "UNKNOWN",
    deterministic_algorithm: str = "",
) -> ExtractedContext:
    """Extract static contextual clues around the finding without code execution."""
    surrounding_text = source_excerpt

    # If repository root is available and line numbers exist, read extended context safely
    if root_path is not None and start_line is not None:
        try:
            full_file = root_path / file_path
            if full_file.is_file():
                lines = full_file.read_text(encoding="utf-8", errors="replace").splitlines()
                # Grab bounded window: 15 lines before and after
                lo = max(0, start_line - 16)
                hi = min(len(lines), start_line + 15)
                surrounding_text = "\n".join(lines[lo:hi])
        except OSError:
            surrounding_text = source_excerpt

    # Gather search corpus for tokens: path, function, class, and code window
    corpus = f"{file_path} {enclosing_function or ''} {enclosing_class or ''} {module_name or ''} {surrounding_text}"
    tokens = _tokenize(corpus)

    semantic_clues: list[str] = []
    inferred_role: ContextualRole = ContextualRole.UNKNOWN

    is_hash = (
        deterministic_role.upper() == "HASH"
        or "SHA" in deterministic_algorithm.upper()
        or "MD5" in deterministic_algorithm.upper()
        or "BLAKE" in deterministic_algorithm.upper()
    )
    is_signing = (
        deterministic_role.upper() == "DIGITAL_SIGNATURE"
        or "ECDSA" in deterministic_algorithm.upper()
        or "ED25519" in deterministic_algorithm.upper()
        or "RSA" in deterministic_algorithm.upper()
    )
    is_agreement = (
        deterministic_role.upper() == "KEY_ESTABLISHMENT"
        or "ECDH" in deterministic_algorithm.upper()
        or "X25519" in deterministic_algorithm.upper()
    )

    if is_hash:
        ca_matches = tokens & CONTENT_ADDRESSING_CLUES
        if ca_matches:
            semantic_clues.extend(f"content_addressing:{c}" for c in sorted(ca_matches))
            inferred_role = ContextualRole.CONTENT_ADDRESSING
        else:
            di_matches = tokens & DATA_INTEGRITY_CLUES
            if di_matches:
                semantic_clues.extend(f"data_integrity:{c}" for c in sorted(di_matches))
                inferred_role = ContextualRole.DATA_INTEGRITY
            else:
                pw_matches = tokens & PASSWORD_CLUES
                if pw_matches:
                    semantic_clues.extend(f"password_derivation:{c}" for c in sorted(pw_matches))
                    inferred_role = ContextualRole.PASSWORD_DERIVATION
                else:
                    inferred_role = ContextualRole.HASHING
    elif is_agreement:
        ka_matches = tokens & KEY_ESTABLISHMENT_CLUES
        if ka_matches:
            semantic_clues.extend(f"key_establishment:{c}" for c in sorted(ka_matches))
        inferred_role = ContextualRole.KEY_ESTABLISHMENT
    elif is_signing:
        fw_matches = tokens & FIRMWARE_SIGNING_CLUES
        if fw_matches:
            semantic_clues.extend(f"firmware_signing:{c}" for c in sorted(fw_matches))
        inferred_role = ContextualRole.DIGITAL_SIGNATURE
    else:
        inferred_role = ContextualRole.UNKNOWN

    summary_parts = [f"File: {file_path}"]
    if enclosing_function:
        summary_parts.append(f"Function: {enclosing_function}")
    if enclosing_class:
        summary_parts.append(f"Class: {enclosing_class}")
    if semantic_clues:
        summary_parts.append(f"Semantic clues: {', '.join(semantic_clues[:5])}")

    return ExtractedContext(
        finding_fingerprint=finding_fingerprint,
        file_path=file_path,
        enclosing_function=enclosing_function,
        enclosing_class=enclosing_class,
        module_name=module_name,
        surrounding_code=surrounding_text[:2000],
        semantic_clues=tuple(semantic_clues),
        inferred_role_candidate=inferred_role,
        context_summary="; ".join(summary_parts),
    )
