from pathlib import Path


ROOT = Path(__file__).parents[1]
README = (ROOT / "README.md").read_text()
CLI_SKILL = (ROOT / "truffile/skills/truffile-cli/SKILL.md").read_text()
CHAT_SKILL = (ROOT / "truffile/skills/truffile-chat/SKILL.md").read_text()
APP_SKILL = (ROOT / "truffile/skills/truffle-app-creator/SKILL.md").read_text()


def test_setup_prompt_is_goal_first_and_names_human_boundaries():
    single_line = README.replace("\n> ", " ").replace("\n", " ")
    assert "then **<goal>**" in single_line
    assert "Do not stop after setup" in single_line
    assert "User ID from Symphony Settings" in single_line
    assert "approval on the physical" in single_line


def test_cli_skill_prefers_machine_contract_and_safe_deletion():
    assert "truffile doctor --json" in CLI_SKILL
    assert "truffile scan --json --non-interactive" in CLI_SKILL
    assert '--user-id "$TRUFFLE_USER_ID"' in CLI_SKILL
    assert "delete my-app --dry-run --json --non-interactive" in CLI_SKILL
    assert "delete my-app --yes --json --non-interactive" in CLI_SKILL
    assert "Settings >\nAbout" not in CLI_SKILL


def test_chat_skill_documents_bounded_compact_output():
    assert "--max-output-bytes" in CHAT_SKILL
    assert "--include-thinking" in CHAT_SKILL
    assert "--include-tools" in CHAT_SKILL
    assert "interrupt a known task" in CHAT_SKILL
    assert "Reserved:" not in CHAT_SKILL


def test_app_creator_keeps_working_before_device_pairing():
    assert "finish the\nlocal app, tests, validation, and dry-run" in APP_SKILL
    assert "truffile create my-app --path ./apps --json --non-interactive" in APP_SKILL
