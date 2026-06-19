from pathlib import Path

from truffile.cli.deploy import _non_interactive_blockers, _plan_json


def test_non_interactive_blockers_allow_welcome_but_block_text_and_oauth():
    plan = {
        "ordered_steps": [
            {"type": "welcome", "name": "Hello"},
            {"type": "files", "name": "Copy"},
            {"type": "text", "name": "API key"},
            {"type": "oauth", "name": "Sign in"},
        ]
    }

    assert _non_interactive_blockers(plan) == [
        {"type": "text", "name": "API key"},
        {"type": "oauth", "name": "Sign in"},
    ]


def test_plan_json_is_compact_for_agents():
    plan = {
        "name": "Smoke",
        "bundle_id": "org.truffle.smoke",
        "finish_label": "foreground",
        "files_to_upload": [
            {"source": "./app.py", "destination": "./app.py"},
        ],
        "bash_commands": [("Install", "pip install -r requirements.txt")],
    }

    assert _plan_json(plan, Path("/tmp/smoke")) == {
        "name": "Smoke",
        "bundle_id": "org.truffle.smoke",
        "mode": "foreground",
        "app_dir": "/tmp/smoke",
        "files": [{"source": "./app.py", "destination": "./app.py"}],
        "bash_steps": ["Install"],
    }
