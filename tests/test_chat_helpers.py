import base64
import sys
import unittest


def _import_chat():
    """lazy import to handle missing deps gracefully"""
    try:
        from truffile.cli import infer
        return infer
    except ImportError:
        return None


class TestParseOnOff(unittest.TestCase):
    def setUp(self):
        self.chat = _import_chat()
        if self.chat is None:
            self.skipTest("chat module not importable")

    def test_true_values(self):
        for val in ["on", "true", "1", "yes", "ON", "True", "YES"]:
            self.assertTrue(self.chat._parse_on_off(val), f"{val} should be True")

    def test_false_values(self):
        for val in ["off", "false", "0", "no", "OFF", "False", "NO"]:
            self.assertFalse(self.chat._parse_on_off(val), f"{val} should be False")

    def test_invalid_returns_none(self):
        self.assertIsNone(self.chat._parse_on_off("maybe"))
        self.assertIsNone(self.chat._parse_on_off(""))
        self.assertIsNone(self.chat._parse_on_off("2"))


class TestMakeUserMessage(unittest.TestCase):
    def setUp(self):
        self.chat = _import_chat()
        if self.chat is None:
            self.skipTest("chat module not importable")

    def test_text_only(self):
        msg = self.chat._make_user_message("hello", None)
        self.assertEqual(msg["role"], "user")

    def test_with_image(self):
        msg = self.chat._make_user_message("describe", "data:image/png;base64,abc")
        self.assertEqual(msg["role"], "user")
        content = msg["content"]
        self.assertIsInstance(content, list)


class TestToDataUrl(unittest.TestCase):
    def setUp(self):
        self.chat = _import_chat()
        if self.chat is None:
            self.skipTest("chat module not importable")

    def test_encodes_correctly(self):
        result = self.chat._to_data_url(b"hello world", "image/png")
        self.assertTrue(result.startswith("data:image/png;base64,"))
        encoded = result.split(",")[1]
        self.assertEqual(base64.b64decode(encoded), b"hello world")


class TestBuildDefaultTools(unittest.TestCase):
    def setUp(self):
        self.chat = _import_chat()
        if self.chat is None:
            self.skipTest("chat module not importable")

    def test_returns_list(self):
        tools = self.chat._build_default_tools()
        self.assertIsInstance(tools, list)
        self.assertTrue(len(tools) > 0)

    def test_tools_have_schema(self):
        tools = self.chat._build_default_tools()
        for tool in tools:
            self.assertEqual(tool["type"], "function")
            self.assertIn("name", tool["function"])
            self.assertIn("parameters", tool["function"])


class TestReplCommands(unittest.TestCase):
    def setUp(self):
        self.chat = _import_chat()
        if self.chat is None:
            self.skipTest("chat module not importable")

    def test_commands_exist(self):
        self.assertIn("/help", self.chat.REPL_COMMANDS)
        self.assertIn("/exit", self.chat.REPL_COMMANDS)
        self.assertIn("/mcp", self.chat.REPL_COMMANDS)
