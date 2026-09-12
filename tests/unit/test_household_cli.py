"""`plan init` / `plan check` / `plan context` against a scratch household directory."""

import shutil
from pathlib import Path

from click.testing import CliRunner

from finplan.cli.household import EXAMPLES, MARKER
from finplan.cli.main import cli


def _init(tmp_path: Path) -> Path:
    home = tmp_path / "money"
    r = CliRunner().invoke(cli, ["init", str(home), "--name", "test-household"])
    assert r.exit_code == 0, r.output
    return home


def test_init_scaffolds_household_directory(tmp_path: Path):
    home = _init(tmp_path)
    for rel in ("scenarios/overlays/.gitkeep", "scenarios/sweeps/.gitkeep", "snapshots",
                "inbox/processed", "runs", "knowledge/decisions.md", "knowledge/glossary.md",
                "scenarios/examples/base.yaml", ".gitignore", "CLAUDE.md", MARKER):
        assert (home / rel).exists(), rel
    assert 'name = "test-household"' in (home / MARKER).read_text(encoding="utf-8")
    assert "test-household" in (home / "CLAUDE.md").read_text(encoding="utf-8")
    assert "snapshots/" in (home / ".gitignore").read_text(encoding="utf-8")
    assert "/finplan:interview" in CliRunner().invoke(cli, ["init", str(tmp_path / "x")]).output
    again = CliRunner().invoke(cli, ["init", str(home)])
    assert again.exit_code != 0 and "already" in again.output


def test_check_and_context_on_fresh_household(tmp_path: Path, monkeypatch):
    home = _init(tmp_path)
    monkeypatch.chdir(home)
    r = CliRunner().invoke(cli, ["check"])
    assert r.exit_code == 0, r.output
    assert "no scenarios/base.yaml yet" in r.output
    r = CliRunner().invoke(cli, ["context"])
    assert r.exit_code == 0, r.output
    assert "household: test-household" in r.output
    assert "run /finplan:interview" in r.output


def test_check_validates_overlays_and_flags_privacy(tmp_path: Path, monkeypatch):
    home = _init(tmp_path)
    monkeypatch.chdir(home)
    shutil.copyfile(EXAMPLES / "base.yaml", home / "scenarios" / "base.yaml")
    shutil.copyfile(EXAMPLES / "retire_55.yaml", home / "scenarios" / "overlays" / "retire_55.yaml")
    r = CliRunner().invoke(cli, ["check"])
    assert r.exit_code == 0, r.output
    assert "2 config(s) validated" in r.output

    (home / "scenarios" / "overlays" / "spend_bad.yaml").write_text(
        "meta: {name: spend_bad, description: broken}\naccounts:\n  - {id: nope}\n",
        encoding="utf-8")
    (home / "knowledge" / "facts.md").write_text("SSN 123-45-6789\n", encoding="utf-8")
    r = CliRunner().invoke(cli, ["check"])
    assert r.exit_code == 1
    assert "base.yaml + spend_bad.yaml" in r.output
    assert "facts.md:1: SSN-like number" in r.output

    r = CliRunner().invoke(cli, ["context"])
    assert "base plan: scenarios/base.yaml, 2 overlays" in r.output
    assert "overlay families: retire, spend" in r.output
