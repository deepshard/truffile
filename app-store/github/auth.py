from __future__ import annotations

import os


class GitHubAuth:
    """Loads a GitHub access token from the ``GITHUB_ACCESS_TOKEN`` env var.

    The installer collects the token via a ``text`` step in ``truffile.yaml``
    (users create a personal access token at https://github.com/settings/tokens).
    """

    def __init__(self, read_only: bool = False) -> None:
        # ``read_only`` is accepted for API compatibility with older callers
        # that used the OAuth-backed auth; the env-var path has no write side.
        self._read_only = read_only

    def load_access_token(self) -> str:
        token = os.getenv("GITHUB_ACCESS_TOKEN", "").strip()
        if not token:
            raise RuntimeError(
                "GITHUB_ACCESS_TOKEN is not set. "
                "Reinstall the app and provide a GitHub personal access token."
            )
        return token
