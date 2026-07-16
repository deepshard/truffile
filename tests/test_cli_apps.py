from truffile.cli.apps import _app_summary, _resolve_delete_selection


APPS = [
    ("focus", "uuid-alpha", "Alpha App", ""),
    ("ambient", "uuid-beta", "Beta Search", ""),
    ("both", "uuid-gamma", "Gamma Search", ""),
]


class _App:
    def __init__(self, *, foreground: bool, background: bool) -> None:
        self.metadata = type("Metadata", (), {"name": "App", "bundle_id": "org.truffle.app"})()
        self.uuid = "uuid-app"
        self.fields = {"foreground": foreground, "background": background}

    def HasField(self, name: str) -> bool:
        return self.fields[name]


def test_app_summaries_add_canonical_type_without_removing_legacy_kind():
    expected = {
        (True, False): ("foreground", "focus"),
        (False, True): ("background", "ambient"),
        (True, True): ("hybrid", "both"),
    }
    for fields, (app_type, legacy_kind) in expected.items():
        summary = _app_summary(_App(foreground=fields[0], background=fields[1]))
        assert summary["type"] == app_type
        assert summary["kind"] == legacy_kind


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
