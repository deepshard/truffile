from pathlib import Path


ROOT = Path(__file__).parents[1]
README = (ROOT / "README.md").read_text()
CLI_SKILL = (ROOT / "truffile/skills/truffile-cli/SKILL.md").read_text()
CHAT_SKILL = (ROOT / "truffile/skills/truffile-chat/SKILL.md").read_text()
APP_SKILL = (ROOT / "truffile/skills/truffle-app-creator/SKILL.md").read_text()


def compact(text: str) -> str:
    return " ".join(text.split())


def test_setup_prompt_is_goal_first_and_names_human_boundaries():
    prompt = compact(README)
    assert "then **<what you want to do with your Truffle>**" in prompt
    assert "Continue through all work that does not need me" in prompt
    assert "follow only the copied skills relevant to the task" in prompt
    assert "Symphony onboarding or my User ID" in prompt
    assert "approval on the physical" in prompt


def test_cli_skill_prefers_machine_contract_and_safe_deletion():
    assert "truffile doctor --json" in CLI_SKILL
    assert "truffile scan --json --non-interactive" in CLI_SKILL
    assert '--user-id "$TRUFFLE_USER_ID"' in CLI_SKILL
    assert "delete my-app --dry-run --json --non-interactive" in CLI_SKILL
    assert "delete my-app --yes --json --non-interactive" in CLI_SKILL
    assert "Settings >\nAbout" not in CLI_SKILL
    assert "### Running inside a Truffle app container" in CLI_SKILL


def test_chat_skill_documents_bounded_compact_output():
    assert "--max-output-bytes" in CHAT_SKILL
    assert "--include-thinking" in CHAT_SKILL
    assert "--include-tools" in CHAT_SKILL
    assert "interrupt a known task" in CHAT_SKILL
    assert "task_not_waiting" in CHAT_SKILL
    assert "pending_user_response" in CHAT_SKILL
    assert "Reserved:" not in CHAT_SKILL


def test_app_creator_keeps_working_before_device_pairing():
    assert "finish the local app, tests, validation, and dry-run" in compact(APP_SKILL)
    assert "truffile create my-app --path ./apps --json --non-interactive" in APP_SKILL
    assert "Ask the user which approach they prefer" not in APP_SKILL
    assert "Ask the user if they want to add skills" not in APP_SKILL
