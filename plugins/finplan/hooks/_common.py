"""Shared helpers for the finplan plugin hooks.

A directory is a finplan *household directory* when it carries a `finplan.toml` marker
(written by `plan init`) or, for directories set up before that command existed, a
`scenarios/base.yaml`. Outside a household directory every hook is silent, so the plugin
can stay enabled globally without touching other projects.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


def read_event() -> dict:
    try:
        raw = sys.stdin.read()
    except Exception:
        return {}
    if not raw.strip():
        return {}
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {}


def household_dir(event: dict) -> Path | None:
    cwd = Path(event.get("cwd") or Path.cwd()).resolve()
    for d in (cwd, *cwd.parents):
        if (d / "finplan.toml").exists() or (d / "scenarios" / "base.yaml").exists():
            return d
    return None
