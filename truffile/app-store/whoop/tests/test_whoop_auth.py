from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from config import WhoopConfig
from whoop_auth import WhoopOAuth


class TestWhoopOAuth(unittest.TestCase):
    def test_uses_installer_oauth_state_app_var_key(self) -> None:
        self.assertEqual(WhoopOAuth.APP_VAR_KEY, "oauth_state")

    def test_prefers_app_var_and_mirrors_token_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            token_file = Path(tmp) / "oauth.json"
            token_file.write_text(json.dumps({"access_token": "from-file"}), encoding="utf-8")
            auth = WhoopOAuth(
                WhoopConfig(token_store_path=token_file),
            )

            with (
                patch.object(auth, "_load_serialized_from_app_var", return_value=json.dumps({"access_token": "from-app-var"})),
                patch.object(auth, "_save_serialized_to_app_var") as save_app_var,
            ):
                payload = auth.get_oauth_payload()

            self.assertEqual(payload, {"access_token": "from-app-var"})
            self.assertEqual(json.loads(token_file.read_text(encoding="utf-8")), {"access_token": "from-app-var"})
            save_app_var.assert_not_called()

    def test_falls_back_to_token_file_when_app_var_unavailable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            token_file = Path(tmp) / "oauth.json"
            token_file.write_text(json.dumps({"access_token": "from-file"}), encoding="utf-8")
            auth = WhoopOAuth(
                WhoopConfig(token_store_path=token_file),
            )

            with patch.object(auth, "_load_serialized_from_app_var", return_value=None):
                payload = auth.get_oauth_payload()

            self.assertEqual(payload, {"access_token": "from-file"})


if __name__ == "__main__":
    unittest.main()
