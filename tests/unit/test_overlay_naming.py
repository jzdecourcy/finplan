"""Overlay naming convention: snake_case <family>_<value> file stems, meta.name equal to
the stem, and a one-line meta.description. The framework ships example overlays in
package data; a household's own overlays are checked by `plan check` in that directory."""

from pathlib import Path

from finplan.cli.household import EXAMPLES, _example_overlays, naming_problems


def test_example_overlays_follow_naming_convention():
    files = _example_overlays()
    assert files, f"no example overlays found under {EXAMPLES}"
    assert naming_problems(files) == []


def test_naming_problems_reports_each_violation(tmp_path: Path):
    bad = tmp_path / "BadName.yaml"
    bad.write_text("meta: {name: other}\n", encoding="utf-8")
    problems = naming_problems([bad])
    assert any("snake_case" in p for p in problems)
    assert any("meta.name" in p for p in problems)
    assert any("meta.description" in p for p in problems)
