import time
import unittest

from prompt_toolkit.document import Document
from prompt_toolkit.completion import CompleteEvent

from truffile.cli.commands import SlashCommand, CHAT_COMMANDS, INFER_COMMANDS
from truffile.cli.prompt import SlashCommandCompleter, TrufflePrompt
from truffile.cli.markdown import has_markdown, count_terminal_lines


class TestSlashCommandCompleter(unittest.TestCase):
    def setUp(self):
        self.commands = [
            SlashCommand("/help", "show help"),
            SlashCommand("/history", "show history"),
            SlashCommand("/reset", "clear history"),
            SlashCommand("/models", "switch model"),
        ]
        self.completer = SlashCommandCompleter(self.commands)
        self.event = CompleteEvent()

    def _complete(self, text: str) -> list[str]:
        doc = Document(text, len(text))
        return [c.text for c in self.completer.get_completions(doc, self.event)]

    def test_slash_yields_all(self):
        results = self._complete("/")
        self.assertEqual(len(results), 4)

    def test_prefix_match(self):
        results = self._complete("/he")
        self.assertEqual(results, ["/help"])

    def test_prefix_match_multiple(self):
        results = self._complete("/h")
        self.assertEqual(set(results), {"/help", "/history"})

    def test_no_slash_yields_nothing(self):
        results = self._complete("hello")
        self.assertEqual(results, [])

    def test_empty_yields_nothing(self):
        results = self._complete("")
        self.assertEqual(results, [])

    def test_space_after_command_yields_nothing(self):
        results = self._complete("/help something")
        self.assertEqual(results, [])

    def test_completions_have_descriptions(self):
        doc = Document("/he", 3)
        completions = list(self.completer.get_completions(doc, self.event))
        self.assertEqual(len(completions), 1)
        self.assertIn("show help", str(completions[0].display_meta))


class TestCommandRegistries(unittest.TestCase):
    def test_chat_commands_have_help_and_exit(self):
        names = [c.name for c in CHAT_COMMANDS]
        self.assertIn("/help", names)
        self.assertIn("/exit", names)

    def test_infer_commands_have_help_and_exit(self):
        names = [c.name for c in INFER_COMMANDS]
        self.assertIn("/help", names)
        self.assertIn("/exit", names)

    def test_all_commands_start_with_slash(self):
        for cmd in CHAT_COMMANDS + INFER_COMMANDS:
            self.assertTrue(cmd.name.startswith("/"), f"{cmd.name} missing /")

    def test_all_commands_have_descriptions(self):
        for cmd in CHAT_COMMANDS + INFER_COMMANDS:
            self.assertTrue(len(cmd.description) > 0, f"{cmd.name} missing description")


class TestDoubleCtrlC(unittest.TestCase):
    def test_single_press_returns_empty_string(self):
        prompt = TrufflePrompt("> ", [])
        result = prompt._handle_ctrlc()
        self.assertEqual(result, "")

    def test_double_press_within_timeout_returns_none(self):
        prompt = TrufflePrompt("> ", [])
        prompt._handle_ctrlc()
        result = prompt._handle_ctrlc()
        self.assertIsNone(result)

    def test_press_after_timeout_resets(self):
        prompt = TrufflePrompt("> ", [])
        prompt._handle_ctrlc()
        prompt._ctrlc_time = time.monotonic() - 5.0
        result = prompt._handle_ctrlc()
        self.assertEqual(result, "")


class TestHasMarkdown(unittest.TestCase):
    def test_code_block(self):
        self.assertTrue(has_markdown("hello\n```python\nprint(1)\n```"))

    def test_header(self):
        self.assertTrue(has_markdown("# Header"))

    def test_h2(self):
        self.assertTrue(has_markdown("## Section"))

    def test_bold(self):
        self.assertTrue(has_markdown("This is **bold** text"))

    def test_unordered_list(self):
        self.assertTrue(has_markdown("- item one\n- item two"))

    def test_ordered_list(self):
        self.assertTrue(has_markdown("1. first\n2. second"))

    def test_link(self):
        self.assertTrue(has_markdown("See [docs](https://example.com)"))

    def test_plain_text(self):
        self.assertFalse(has_markdown("hello world"))

    def test_empty(self):
        self.assertFalse(has_markdown(""))

    def test_single_asterisk(self):
        self.assertFalse(has_markdown("I like * stars"))


class TestCountTerminalLines(unittest.TestCase):
    def test_single_line(self):
        self.assertEqual(count_terminal_lines("hello", 80), 1)

    def test_two_lines(self):
        self.assertEqual(count_terminal_lines("hello\nworld", 80), 2)

    def test_empty_line(self):
        self.assertEqual(count_terminal_lines("", 80), 1)

    def test_wrapping(self):
        self.assertEqual(count_terminal_lines("a" * 160, 80), 2)

    def test_exact_width(self):
        self.assertEqual(count_terminal_lines("a" * 80, 80), 1)


if __name__ == "__main__":
    unittest.main()
