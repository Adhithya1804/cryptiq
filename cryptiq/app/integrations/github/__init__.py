"""GitHub source provider.

The engine never imports this package. It receives a SourceSnapshot and has no
knowledge of where the source came from.
"""

from app.integrations.github.client import GitHubSourceProvider
from app.integrations.github.models import PROVIDER, GitHubCommit
from app.integrations.github.validator import parse_repository_url

__all__ = ["PROVIDER", "GitHubCommit", "GitHubSourceProvider", "parse_repository_url"]
