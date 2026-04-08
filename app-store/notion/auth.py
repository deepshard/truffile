from __future__ import annotations

import os


class NotionAuth:
    """Loads a Notion integration token from the ``NOTION_ACCESS_TOKEN`` env var.

    The installer collects the token via a ``text`` step in ``truffile.yaml``
    (users create an internal integration at https://notion.so/profile/integrations).
    """

    def __init__(self, read_only: bool = False) -> None:
        # ``read_only`` is accepted for API compatibility with older callers.
        self._read_only = read_only

    def get_access_token(self) -> str:
        token = os.getenv("NOTION_ACCESS_TOKEN", "").strip()
        if not token:
            raise RuntimeError(
                "NOTION_ACCESS_TOKEN is not set. "
                "Reinstall the app and provide a Notion internal integration token."
            )
        return token
