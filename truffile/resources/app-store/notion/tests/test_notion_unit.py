from __future__ import annotations

import importlib
import json
import os
import sys
import unittest
from unittest.mock import MagicMock, patch


class TestNotionAuth(unittest.TestCase):
    def test_get_access_token_reads_env(self) -> None:
        sys.modules.pop("auth", None)
        notion_auth = importlib.import_module("auth")
        with patch.dict(os.environ, {"NOTION_ACCESS_TOKEN": "ntn_env_token"}, clear=False):
            self.assertEqual(notion_auth.NotionAuth().get_access_token(), "ntn_env_token")

    def test_missing_env_raises(self) -> None:
        sys.modules.pop("auth", None)
        notion_auth = importlib.import_module("auth")
        env = {k: v for k, v in os.environ.items() if k != "NOTION_ACCESS_TOKEN"}
        with patch.dict(os.environ, env, clear=True):
            with self.assertRaises(RuntimeError):
                notion_auth.NotionAuth().get_access_token()


class TestNotionClient(unittest.TestCase):
    def test_verify_notion_workspace_parses_workspace_name(self) -> None:
        sys.modules.pop("notion_client", None)
        notion_client = importlib.import_module("notion_client")

        payload = {
            "bot": {
                "workspace_name": "Team Space",
            }
        }
        response = MagicMock()
        response.read.return_value = json.dumps(payload).encode("utf-8")
        response.__enter__.return_value = response
        response.__exit__.return_value = False

        with patch.object(notion_client.urlrequest, "urlopen", return_value=response):
            ok, message = notion_client.verify_notion_workspace("ntn_test_token")

        self.assertTrue(ok)
        self.assertIn("Team Space", message)


if __name__ == "__main__":
    unittest.main()
