from truffile.cli.apps import _resolve_delete_selection


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
