from types import SimpleNamespace

from truffile.cli.apps import _resolve_delete_selection, cmd_list
from truffile.storage import StoredDevice, StoredState


APPS = [
    ("focus", "uuid-alpha", "Alpha App", ""),
    ("ambient", "uuid-beta", "Beta Search", ""),
    ("both", "uuid-gamma", "Gamma Search", ""),
]


def test_resolve_delete_selection_numbers_still_work():
    indices, error = _resolve_delete_selection("1, 3", APPS)

    assert indices == [0, 2]
    assert error is None


def test_resolve_delete_selection_name():
    indices, error = _resolve_delete_selection("Alpha App", APPS)

    assert indices == [0]
    assert error is None


def test_resolve_delete_selection_slug():
    indices, error = _resolve_delete_selection("alpha-app", APPS)

    assert indices == [0]
    assert error is None


def test_resolve_delete_selection_uuid():
    indices, error = _resolve_delete_selection("uuid-beta", APPS)

    assert indices == [1]
    assert error is None


def test_resolve_delete_selection_ambiguous_substring():
    indices, error = _resolve_delete_selection("Search", APPS)

    assert indices is None
    assert error
    assert "Ambiguous" in error


def test_resolve_delete_selection_multiple_names():
    indices, error = _resolve_delete_selection("Alpha App, Gamma Search", APPS)

    assert indices == [0, 2]
    assert error is None


def test_list_devices_json_is_machine_readable(capsys):
    storage = SimpleNamespace(
        state=StoredState(
            devices=[StoredDevice(name="truffle-1234", token="token")],
            last_used_device="truffle-1234",
        ),
        list_devices=lambda: ["truffle-1234"],
    )

    result = cmd_list(SimpleNamespace(what="devices", json=True), storage)

    assert result == 0
    assert capsys.readouterr().out == (
        '{\n  "devices": [\n    {\n      "name": "truffle-1234",\n'
        '      "active": true\n    }\n  ]\n}\n'
    )
