"""Household-directory commands: `plan init`, `plan check`, `plan context`.

A *household directory* is any folder that holds one household's plan: scenarios/,
snapshots/, inbox/, runs/, knowledge/, and a `finplan.toml` marker. The engine is
installed separately (pip) and the Claude Code plugin separately again; nothing personal
ever lives in either of those. Every `plan` command is cwd-relative, so these commands
work from the household directory itself.
"""

from __future__ import annotations

import datetime as dt
import json
import re
import shutil
from pathlib import Path

import click
import yaml

from finplan import __version__
from finplan.config.loader import load_scenario

DATA = Path(__file__).resolve().parent.parent / "data"
TEMPLATES = DATA / "household"
EXAMPLES = DATA / "examples"
MARKER = "finplan.toml"
PLUGIN_INSTALL = ("/plugin marketplace add jzdecourcy/finplan",
                  "/plugin install finplan@finplan")

_STEM = re.compile(r"^[a-z0-9]+(_[a-z0-9]+)+$")
_PRIVACY = [
    ("SSN-like number", re.compile(r"\b\d{3}-\d{2}-\d{4}\b")),
    ("9+ digit number (account number?)", re.compile(r"(?<![\d.,$-])\d{9,}(?![\d.,])")),
    ("credential", re.compile(r"(?i)\b(password|passcode|passphrase)\s*[:=]")),
]


def find_household(start: Path | None = None) -> Path | None:
    """Nearest ancestor (inclusive) carrying the marker or a scenarios/base.yaml."""
    cwd = (start or Path.cwd()).resolve()
    for d in (cwd, *cwd.parents):
        if (d / MARKER).exists() or (d / "scenarios" / "base.yaml").exists():
            return d
    return None


# ---------------------------------------------------------------- plan init

def _copy_tree(src: Path, dst: Path, pattern: str) -> list[Path]:
    written = []
    dst.mkdir(parents=True, exist_ok=True)
    for f in sorted(src.glob(pattern)):
        target = dst / f.name
        if not target.exists():
            shutil.copyfile(f, target)
            written.append(target)
    return written


@click.command()
@click.argument("directory", type=click.Path(), default=".")
@click.option("--name", default=None, help="household name (default: directory name)")
def init(directory: str, name: str | None) -> None:
    """Scaffold a household directory: folders, templates, marker, gitignore."""
    home = Path(directory).resolve()
    if (home / MARKER).exists():
        raise click.UsageError(f"{home} is already a household directory ({MARKER} exists)")
    home.mkdir(parents=True, exist_ok=True)
    name = name or home.name
    for sub in ("scenarios/overlays", "scenarios/sweeps", "snapshots", "inbox/processed",
                "runs", "knowledge"):
        (home / sub).mkdir(parents=True, exist_ok=True)
    for sub in ("scenarios/overlays", "scenarios/sweeps"):
        keep = home / sub / ".gitkeep"
        if not keep.exists():
            keep.write_text("", encoding="utf-8")
    _copy_tree(EXAMPLES, home / "scenarios" / "examples", "*.yaml")
    _copy_tree(TEMPLATES / "knowledge", home / "knowledge", "*.md")
    gitignore = home / ".gitignore"
    if not gitignore.exists():
        gitignore.write_text((TEMPLATES / "gitignore").read_text(encoding="utf-8"),
                             encoding="utf-8")
    claude_md = home / "CLAUDE.md"
    if not claude_md.exists():
        tpl = (TEMPLATES / "CLAUDE.md").read_text(encoding="utf-8")
        claude_md.write_text(tpl.replace("{name}", name), encoding="utf-8")
    (home / MARKER).write_text(
        "[household]\n"
        f'name = "{name}"\n'
        f'created = "{dt.date.today().isoformat()}"\n'
        f'engine = "{__version__}"\n',
        encoding="utf-8",
    )
    click.echo(f"household directory ready: {home}\n")
    click.echo("next steps:")
    click.echo("  1. install the finplan plugin in Claude Code (once per machine):")
    for line in PLUGIN_INSTALL:
        click.echo(f"       {line}")
    click.echo("  2. open Claude Code in this directory and run /finplan:interview")
    click.echo("  3. (optional) git init here and keep the repo PRIVATE; snapshots/, inbox/ and")
    click.echo("     runs/ are already gitignored")
    click.echo("\nsmoke test: plan run -f scenarios/examples/base.yaml")


# ---------------------------------------------------------------- plan check

def naming_problems(files: list[Path]) -> list[str]:
    problems = []
    for f in files:
        data = yaml.safe_load(f.read_text(encoding="utf-8")) or {}
        meta = data.get("meta") or {}
        if not _STEM.match(f.stem):
            problems.append(f"{f.name}: stem is not <family>_<value> snake_case")
        if meta.get("name") != f.stem:
            problems.append(f"{f.name}: meta.name {meta.get('name')!r} != stem")
        desc = meta.get("description")
        if not desc or not isinstance(desc, str) or len(desc) > 120:
            problems.append(f"{f.name}: meta.description missing or over 120 chars")
    return problems


def privacy_problems(home: Path) -> list[str]:
    problems = []
    targets = [home / "CLAUDE.md", home / "README.md"]
    for sub in ("scenarios", "knowledge"):
        targets += sorted((home / sub).rglob("*")) if (home / sub).exists() else []
    for f in targets:
        if not f.is_file() or f.suffix not in (".yaml", ".yml", ".md", ".txt", ".toml"):
            continue
        try:
            text = f.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            problems.append(f"{f.relative_to(home)}: not valid UTF-8")
            continue
        for lineno, line in enumerate(text.splitlines(), 1):
            for label, rx in _PRIVACY:
                if rx.search(line):
                    problems.append(f"{f.relative_to(home)}:{lineno}: {label}")
    return problems


def _example_overlays() -> list[Path]:
    out = []
    for f in sorted(EXAMPLES.glob("*.yaml")):
        data = yaml.safe_load(f.read_text(encoding="utf-8")) or {}
        if "sim" in data or "levers" in data:      # base plan or sweep spec
            continue
        out.append(f)
    return out


@click.command()
def check() -> None:
    """Enforce the mechanical rules: overlay naming, every overlay validates, privacy scan."""
    home = find_household() or Path.cwd()
    problems: list[str] = []
    overlays = sorted((home / "scenarios" / "overlays").glob("*.yaml"))
    problems += naming_problems(overlays)
    base = home / "scenarios" / "base.yaml"
    if base.exists():
        stacks = [[base]] + [[base, ov] for ov in overlays]
        for stack in stacks:
            try:
                load_scenario([str(p) for p in stack])
            except Exception as e:  # ConfigError or pydantic ValidationError
                label = " + ".join(p.name for p in stack)
                first = str(e).strip().splitlines()[0] if str(e).strip() else type(e).__name__
                problems.append(f"{label}: {first}")
    else:
        click.echo("no scenarios/base.yaml yet (run /finplan:interview); skipping validation")
    problems += privacy_problems(home)
    n_checked = len(overlays) + (1 if base.exists() else 0)
    if problems:
        click.echo(f"plan check: {len(problems)} problem(s) across {n_checked} config(s)")
        for p in problems:
            click.echo(f"  - {p}")
        raise SystemExit(1)
    click.echo(f"plan check OK: {n_checked} config(s) validated, naming and privacy clean")


# ---------------------------------------------------------------- plan context

def _latest_date_in(path: Path) -> str | None:
    if not path.exists():
        return None
    text = path.read_text(encoding="utf-8", errors="replace")
    text = re.sub(r"<!--.*?-->", "", text, flags=re.S)     # template examples live in comments
    dates = re.findall(r"\b(20\d{2}-\d{2}-\d{2})\b", text)
    return max(dates) if dates else None


@click.command()
def context() -> None:
    """Compact session-start summary: plan, data age, last run, knowledge activity."""
    home = find_household() or Path.cwd()
    name = home.name
    marker = home / MARKER
    if marker.exists():
        m = re.search(r'name\s*=\s*"([^"]*)"', marker.read_text(encoding="utf-8"))
        if m:
            name = m.group(1)
    click.echo(f"household: {name}  (finplan {__version__}, {home})")

    base = home / "scenarios" / "base.yaml"
    overlays = sorted((home / "scenarios" / "overlays").glob("*.yaml"))
    sweeps = sorted((home / "scenarios" / "sweeps").glob("*.yaml"))
    if base.exists():
        click.echo(f"base plan: scenarios/base.yaml, {len(overlays)} overlays, "
                   f"{len(sweeps)} sweep specs")
        if overlays:
            fams = sorted({o.stem.split("_")[0] for o in overlays})
            click.echo(f"overlay families: {', '.join(fams)}")
    else:
        status = home / "knowledge" / "onboarding-status.md"
        state = "in progress" if status.exists() else "not started"
        click.echo(f"base plan: none yet (onboarding {state}; run /finplan:interview)")

    snaps = sorted((home / "snapshots").glob("*.yaml"))
    if snaps:
        try:
            age = (dt.date.today() - dt.date.fromisoformat(snaps[-1].stem)).days
            flag = "  << stale, consider `plan update`" if age > 60 else ""
            click.echo(f"snapshot: {snaps[-1].stem} ({age} days old){flag}")
        except ValueError:
            click.echo(f"snapshot: {snaps[-1].name}")
    else:
        click.echo("snapshot: none yet")

    runs = sorted((home / "runs").glob("*/metrics.json"), key=lambda p: p.stat().st_mtime)
    if runs:
        try:
            met = json.loads(runs[-1].read_text(encoding="utf-8"))
            keys = ("success_probability", "terminal_wealth_real_median",
                    "median_lifetime_tax", "median_first_failure_year")
            bits = [f"{k}={met[k]}" for k in keys if k in met]
            click.echo(f"last run: {runs[-1].parent.name}  {' '.join(bits)}")
        except (json.JSONDecodeError, OSError):
            click.echo(f"last run: {runs[-1].parent.name}")

    for fname in ("decisions.md", "open-questions.md", "assumptions.md"):
        d = _latest_date_in(home / "knowledge" / fname)
        if d:
            click.echo(f"knowledge/{fname}: latest entry {d}")
