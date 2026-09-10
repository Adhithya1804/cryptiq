"""Stable identities for findings and for whole scans.

A fingerprint identifies the same logical finding across commits, so a result
can be tracked, deduplicated and marked as reviewed. It is a hash of canonical
parts only. Line numbers, columns, timestamps and the commit SHA are
deliberately excluded: every one of them changes when the file is edited or a
new commit is scanned, which would make every finding look new and nothing
ever look UNCHANGED or RESOLVED.
"""

import hashlib
from dataclasses import dataclass

_SEPARATOR = "\x1f"


def fingerprint(*parts: str) -> str:
    """Return a hex SHA-256 fingerprint over the given canonical parts.

    Parts are joined with a separator that cannot appear in them, so distinct
    inputs cannot collide by concatenation.
    """
    if not parts:
        raise ValueError("fingerprint requires at least one part")
    if any(_SEPARATOR in part for part in parts):
        raise ValueError("fingerprint parts must not contain the unit separator")
    payload = _SEPARATOR.join(parts).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def finding_fingerprint(
    *,
    repository: str,
    file_path: str,
    rule_id: str,
    algorithm: str,
    api: str,
    operation: str,
    enclosing_function: str | None = None,
    enclosing_class: str | None = None,
) -> str:
    """Return the stable identity of one finding.

    The parts are the ones that survive an edit to the surrounding file: which
    repository, which file, which rule fired, and what cryptographic operation
    was seen where in the program's structure. Adding a line above the call
    does not change any of them, so the finding stays the same finding.

    Each part is written with its own label so that a value moving between
    fields cannot produce the same fingerprint by accident.
    """
    labelled = (
        f"repository={repository.strip().lower()}",
        f"file_path={file_path.strip()}",
        f"rule_id={rule_id.strip()}",
        f"algorithm={algorithm.strip().upper()}",
        f"api={api.strip()}",
        f"operation={operation.strip().upper()}",
        f"function={(enclosing_function or '').strip()}",
        f"class={(enclosing_class or '').strip()}",
    )
    return fingerprint(*labelled)


@dataclass(frozen=True)
class ScanIdentity:
    """What makes two scans the same deterministic analysis.

    The seven parts are exactly the inputs the engine is a pure function of.
    Two scans sharing an identity must produce the same findings, which is
    what allows a completed scan to be served from cache instead of rerun.
    """

    provider: str
    owner: str
    name: str
    commit_sha: str
    parser_version: str
    ruleset_version: str
    pqc_ruleset_version: str

    @property
    def canonical_key(self) -> str:
        """A normalized string form of the identity."""
        return _SEPARATOR.join(
            (
                self.provider.strip().lower(),
                self.owner.strip().lower(),
                self.name.strip().lower(),
                self.commit_sha.strip().lower(),
                self.parser_version.strip(),
                self.ruleset_version.strip(),
                self.pqc_ruleset_version.strip(),
            )
        )

    @property
    def digest(self) -> str:
        """A hex SHA-256 digest of the canonical key."""
        return hashlib.sha256(self.canonical_key.encode("utf-8")).hexdigest()
