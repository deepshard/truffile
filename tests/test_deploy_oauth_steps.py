import json
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from urllib.parse import parse_qs, urlparse

from truffile.deploy.builder import deploy_with_builder
from truffile.deploy.steps.oauth import (
    _build_authorization_url,
    _build_installed_token_payload,
    _parse_callback,
)


class _NoopSpinner:
    def __init__(self, *_args, **_kwargs):
        pass

    def start(self):
        pass

    def stop(self, success=True):
        pass

    def fail(self, _message=None):
        pass


class _NoopLog:
    def __init__(self, *_args, **_kwargs):
        pass

    def add(self, _line):
        pass

    def finish(self):
        pass


class TestOAuthHelpers(unittest.TestCase):
    def test_parse_callback_accepts_full_url_and_checks_state(self):
        code = _parse_callback("https://truffle.net/api/oauth/callback?code=abc&state=state-1", expected_state="state-1")
        self.assertEqual(code, "abc")

    def test_parse_callback_accepts_raw_code(self):
        self.assertEqual(_parse_callback("abc123", expected_state="state-1"), "abc123")

    def test_parse_callback_rejects_state_mismatch(self):
        with self.assertRaisesRegex(RuntimeError, "state"):
            _parse_callback("https://truffle.net/api/oauth/callback?code=abc&state=wrong", expected_state="state-1")

    def test_build_authorization_url_includes_resource_and_pkce(self):
        url = _build_authorization_url(
            auth_endpoint="https://provider.example/auth",
            client_id="client-1",
            redirect_uri="https://truffle.net/api/oauth/callback",
            state="state-1",
            scopes=["read:a", "read:b"],
            oauth_resource="https://mcp.example",
            include_granted_scopes=False,
            code_challenge="challenge",
        )
        parsed = urlparse(url)
        params = parse_qs(parsed.query)
        self.assertEqual(params["client_id"], ["client-1"])
        self.assertEqual(params["scope"], ["read:a read:b"])
        self.assertEqual(params["resource"], ["https://mcp.example"])
        self.assertEqual(params["include_granted_scopes"], ["false"])
        self.assertEqual(params["code_challenge_method"], ["S256"])

    def test_installed_payload_keeps_client_metadata_for_refresh(self):
        payload = _build_installed_token_payload(
            token_response={"access_token": "tok", "refresh_token": "rt", "expires_in": 3600},
            step={"redirect_uri": "https://cb", "scopes": ["offline"]},
            client_registration={"client_id_issued_at": 12},
            client_id="client-1",
            client_secret="secret-1",
            auth_endpoint="https://auth",
            token_endpoint="https://token",
            oauth_resource="https://resource",
        )
        self.assertEqual(payload["client_id"], "client-1")
        self.assertEqual(payload["client_secret"], "secret-1")
        self.assertEqual(payload["redirect_uri"], "https://cb")
        self.assertEqual(payload["token_endpoint"], "https://token")
        self.assertEqual(payload["resource"], "https://resource")
        self.assertIn("expires_at", payload)


class TestOAuthDeployIntegration(unittest.IsolatedAsyncioTestCase):
    async def test_deploy_runs_welcome_and_oauth_and_injects_token_file_env(self):
        class FakeClient:
            def __init__(self):
                self.app_uuid = None
                self.access_path = None
                self.exec_commands = []
                self.exec_stream_commands = []
                self.finished_foreground = None

            async def connect(self):
                pass

            async def start_build(self):
                self.app_uuid = "app-uuid"
                self.access_path = "route-token"

            async def exec(self, cmd, cwd="/"):
                self.exec_commands.append((cmd, cwd))
                return SimpleNamespace(exit_code=0)

            async def exec_stream(self, _cmd, cwd="/"):
                self.exec_stream_commands.append((_cmd, cwd))
                yield "exit", json.dumps({"code": 0})

            async def finish_app(self, **kwargs):
                self.finished_foreground = kwargs["foreground"]
                self.app_uuid = None
                self.access_path = None

            async def discard(self):
                self.app_uuid = None
                self.access_path = None

        config = {
            "metadata": {
                "name": "OAuth App",
                "bundle_id": "org.test.oauth",
                "foreground": {
                    "process": {"cmd": ["python", "app.py"]},
                },
            },
            "steps": [
                {"name": "Welcome", "type": "welcome", "content": "Hello"},
                {
                    "name": "OAuth",
                    "type": "oauth",
                    "provider": "Example",
                    "redirect_uri": "https://truffle.net/api/oauth/callback",
                    "auth_endpoint": "https://provider.example/auth",
                    "token_endpoint": "https://provider.example/token",
                    "client_id": "client-1",
                    "client_secret": "secret-1",
                    "scopes": ["offline"],
                    "token_output_file": "/root/.example/oauth.json",
                    "token_file_env_name": "EXAMPLE_TOKEN_FILE",
                    "update_check": "python ./foreground.py --verify",
                },
                {"name": "Verify", "type": "bash", "run": "python ./foreground.py --verify"},
            ],
        }
        client = FakeClient()

        with (
            patch("builtins.input", side_effect=["", "https://truffle.net/api/oauth/callback?code=code-1&state=state-1"]),
            patch("truffile.deploy.steps.oauth.secrets.token_urlsafe", return_value="state-1"),
            patch(
                "truffile.deploy.steps.oauth._exchange_authorization_code",
                new=AsyncMock(return_value={"access_token": "tok", "refresh_token": "rt"}),
            ),
        ):
            result = await deploy_with_builder(
                client=client,
                config=config,
                app_dir=__import__("pathlib").Path("."),
                app_type="focus",
                device="truffle-test",
                interactive=False,
                spinner_cls=_NoopSpinner,
                scrolling_log_cls=_NoopLog,
                info=lambda _msg: None,
                success=lambda _msg: None,
                error=lambda _msg: None,
                color_dim="",
                color_reset="",
                color_bold="",
                arrow="->",
                interactive_shell=lambda _url: None,
            )

        self.assertEqual(result, 0)
        self.assertIsNotNone(client.finished_foreground)
        self.assertIn("EXAMPLE_TOKEN_FILE=/root/.example/oauth.json", client.finished_foreground["env"])
        self.assertTrue(any("/root/.example/oauth.json" in command for command, _cwd in client.exec_commands))
        self.assertTrue(any("export EXAMPLE_TOKEN_FILE='/root/.example/oauth.json'" in command for command, _cwd in client.exec_stream_commands))
