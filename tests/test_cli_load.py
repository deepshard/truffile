from types import SimpleNamespace

from truffile.cli.load import cmd_load


def test_load_skills_copies_bundled_skills(tmp_path):
    result = cmd_load(SimpleNamespace(what="skills", path=str(tmp_path), force=False, json=False))

    assert result == 0
    assert (tmp_path / "truffile" / "skills" / "truffile-cli" / "SKILL.md").is_file()


def test_load_examples_copies_bundled_examples(tmp_path):
    result = cmd_load(SimpleNamespace(what="examples", path=str(tmp_path), force=False, json=False))

    assert result == 0
    assert (tmp_path / "truffile" / "examples" / "arxiv" / "truffile.yaml").is_file()


def test_load_skips_existing_without_force(tmp_path):
    target = tmp_path / "truffile" / "skills"
    target.mkdir(parents=True)
    marker = target / "marker.txt"
    marker.write_text("keep", encoding="utf-8")

    result = cmd_load(SimpleNamespace(what="skills", path=str(tmp_path), force=False, json=False))

    assert result == 0
    assert marker.read_text(encoding="utf-8") == "keep"
