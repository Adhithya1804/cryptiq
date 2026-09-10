"""The parts of GitHub's API responses Cryptiq relies on."""

from dataclasses import dataclass
from typing import Any

from app.errors import RepositoryUnavailableError

PROVIDER = "github"


@dataclass(frozen=True)
class GitHubCommit:
    """A commit as GitHub reports it.

    Only the SHA is used. Everything else in the response is ignored so a
    change in GitHub's payload cannot affect the analysis.
    """

    sha: str

    @classmethod
    def from_payload(cls, payload: Any) -> "GitHubCommit":
        """Read the SHA out of a commit response."""
        if not isinstance(payload, dict) or not isinstance(payload.get("sha"), str):
            raise RepositoryUnavailableError(
                "The provider returned an unreadable commit response."
            )
        return cls(sha=payload["sha"])
