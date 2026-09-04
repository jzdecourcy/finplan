"""Tax parameter loading + inflation indexing.

Parameter values live in per-year YAML data files (finplan/data/tax/) with cited sources —
never in code. `indexing_rules.yaml` declares which parameter paths index with CPI (and
their statutory rounding); everything else stays fixed nominal, which is the real-world
drag for items like the NIIT and SS-taxation thresholds.
"""

from __future__ import annotations

import copy
from functools import lru_cache
from importlib import resources
from pathlib import Path
from typing import Any

import yaml

_DATA_PKG = "finplan.data.tax"


def _load_data_file(name: str) -> dict:
    path = resources.files(_DATA_PKG) / name
    return yaml.safe_load(path.read_text(encoding="utf-8"))


@lru_cache(maxsize=8)
def load_federal(year: int) -> dict:
    return _load_data_file(f"us_federal_{year}.yaml")


@lru_cache(maxsize=8)
def load_michigan(year: int) -> dict:
    return _load_data_file(f"us_mi_{year}.yaml")


@lru_cache(maxsize=1)
def load_rmd_table() -> dict[int, float]:
    raw = _load_data_file("rmd_uniform_lifetime.yaml")["uniform_lifetime"]
    return {int(k): float(v) for k, v in raw.items()}


@lru_cache(maxsize=1)
def load_indexing_rules() -> dict:
    return _load_data_file("indexing_rules.yaml")


def _round_to(value: float, increment: float | None) -> float:
    if not increment:
        return value
    return round(value / increment) * increment


def _get_path(d: dict, dotted: str):
    node: Any = d
    for part in dotted.split("."):
        if not isinstance(node, dict) or part not in node:
            return None
        node = node[part]
    return node


def _set_path(d: dict, dotted: str, value) -> None:
    parts = dotted.split(".")
    node = d
    for part in parts[:-1]:
        node = node[part]
    node[parts[-1]] = value


def _scale(node, factor: float, round_to: float | None):
    """Scale every numeric leaf under `node` (bracket lists scale their thresholds)."""
    if isinstance(node, (int, float)) and not isinstance(node, bool):
        return _round_to(node * factor, round_to)
    if isinstance(node, list):
        return [_scale(x, factor, round_to) for x in node]
    if isinstance(node, dict):
        return {
            k: (_scale(v, factor, round_to) if k != "rate" else v) for k, v in node.items()
        }
    return node


def index_params(base: dict, cpi_factor: float, rules_key: str) -> dict:
    """Project a parameter file forward by cumulative inflation since the sim start.

    cpi_factor is the simulation path's own cumulative inflation — high-inflation paths
    get higher brackets, matching how the IRS actually indexes.
    """
    if cpi_factor == 1.0:
        return base
    rules = load_indexing_rules().get(rules_key, {})
    out = copy.deepcopy(base)
    for dotted, rule in rules.items():
        if rule.get("index") != "cpi":
            continue
        node = _get_path(out, dotted)
        if node is None:
            continue
        _set_path(out, dotted, _scale(node, cpi_factor, rule.get("round_to")))
    return out
