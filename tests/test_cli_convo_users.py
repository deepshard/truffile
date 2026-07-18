from types import SimpleNamespace

from truffile.cli.convo import _confirm_hard_reset, _reset_mode
from truffile.cli.users import _confirm_clear_other_users, _identity_dict


def test_reset_mode_labels_soft_and_hard():
    assert _reset_mode(SimpleNamespace(hard=False)) == "soft"
    assert _reset_mode(SimpleNamespace(hard=True)) == "hard"


def test_confirm_hard_reset_requires_yes(monkeypatch):
    monkeypatch.setattr("builtins.input", lambda _prompt: "no")
    assert _confirm_hard_reset() is False

    monkeypatch.setattr("builtins.input", lambda _prompt: "yes")
    assert _confirm_hard_reset() is True


def test_identity_dict_handles_missing_username():
    identity = _identity_dict(SimpleNamespace(user_id="abc123", username=""))

    assert identity == {"user_id": "abc123", "username": ""}


def test_confirm_clear_other_users_requires_yes(monkeypatch):
    identity = {"user_id": "abc123", "username": "abd"}

    monkeypatch.setattr("builtins.input", lambda _prompt: "y")
    assert _confirm_clear_other_users(identity) is False

    monkeypatch.setattr("builtins.input", lambda _prompt: "yes")
    assert _confirm_clear_other_users(identity) is True
