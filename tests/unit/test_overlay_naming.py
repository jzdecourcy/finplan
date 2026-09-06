"""Overlay naming convention: snake_case <family>_<value> file stems, meta.name equal to
the stem, and a one-line meta.description. Covers scenarios/overlays/ (personal, may be
absent in a public checkout) and the example overlays under scenarios/examples/ (anything
that isn't a base plan or a sweep spec)."""

import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2] / "scenarios"
STEM = re.compile(r"^[a-z0-9]+(_[a-z0-9]+)+$")


def _overlay_files() -> list[Path]:
    files = sorted((ROOT / "overlays").glob("*.yaml"))
    for f in sorted((ROOT / "examples").glob("*.yaml")):
        data = yaml.safe_load(f.read_text(encoding="utf-8")) or {}
        if "sim" in data or "levers" in data:   # base plan or sweep spec
            continue
        files.append(f)
    return files


def test_overlays_follow_naming_convention():
    problems = []
    for f in _overlay_files():
        data = yaml.safe_load(f.read_text(encoding="utf-8")) or {}
        meta = data.get("meta") or {}
        if not STEM.match(f.stem):
            problems.append(f"{f.name}: stem is not <family>_<value> snake_case")
        if meta.get("name") != f.stem:
            problems.append(f"{f.name}: meta.name {meta.get('name')!r} != stem")
        desc = meta.get("description")
        if not desc or not isinstance(desc, str) or len(desc) > 120:
            problems.append(f"{f.name}: meta.description missing or over 120 chars")
    assert not problems, "\n".join(problems)
