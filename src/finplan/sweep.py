"""Decision-lever sweep.

Cross a grid of *controllable* overlays (retirement age, Roth ladder, guardrail, SS
claim age, house move ...) and run every cell under each *stress* condition (things the
household does not choose: horizon, spending drift, S-corp income). Report a
success-vs-estate frontier rather than a single "best" cell, because success
probability alone is maximised by the trivial answer (work longer, spend less).

Spec file (YAML, lives in scenarios/sweeps/):

    name: decision_grid
    mode: mc            # det | mc | hist
    seed: 42
    paths: 2000
    noise_seeds: 3      # extra seeds run on the top frontier cells to size MC noise
    levers:             # cross product of one option per lever
      retire:
        - { label: r56, overlays: [retire_56] }
        - { label: r57, overlays: [retire_57] }
      ladder:
        - { label: nolad, overlays: [] }
        - { label: lad22, overlays: [roth_ladder_22] }
    stress:             # every cell runs once per condition; the FIRST is the reference
      - { label: base, overlays: [] }
      - { label: spend30, overlays: [spend_plus30] }

Overlay names resolve to <spec dir>/../overlays/<name>.yaml unless they already look
like a path. Lever overlays are stacked in lever order, stress overlays last.
"""

from __future__ import annotations

import itertools
import json
import os
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd
import yaml

from finplan.config.loader import ConfigError

METRIC_COLS = ["success", "median_terminal", "p10_terminal", "lifetime_tax", "first_failure"]


@dataclass
class Option:
    label: str
    overlays: list[str]


@dataclass
class SweepSpec:
    name: str
    levers: dict[str, list[Option]]
    stress: list[Option]
    mode: str = "mc"
    seed: int | None = 42
    paths: int | None = None
    noise_seeds: int = 0
    description: str = ""
    source: Path | None = None
    frontier_within: str | None = None   # lever to condition the frontier on (default: first)
    fixed: list[str] = field(default_factory=list)   # overlays applied to EVERY cell (held constant)


@dataclass
class Cell:
    cell_id: str
    choices: dict[str, str]
    overlays: list[str] = field(default_factory=list)


def _resolve_overlay(name: str, spec_dir: Path) -> str:
    p = Path(name)
    if p.suffix == ".yaml" or "/" in name or "\\" in name:
        return str(p if p.is_absolute() else spec_dir / p)
    candidate = spec_dir.parent / "overlays" / f"{name}.yaml"
    if not candidate.exists():
        raise ConfigError(f"sweep overlay {name!r} not found at {candidate}")
    return str(candidate)


def _options(raw: list, spec_dir: Path, where: str) -> list[Option]:
    out = []
    for item in raw:
        if not isinstance(item, dict) or "label" not in item:
            raise ConfigError(f"{where}: each option needs a label (got {item!r})")
        overlays = item.get("overlays") or []
        out.append(Option(str(item["label"]), [_resolve_overlay(o, spec_dir) for o in overlays]))
    labels = [o.label for o in out]
    if len(set(labels)) != len(labels):
        raise ConfigError(f"{where}: duplicate option labels {labels}")
    return out


def load_spec(path: str | Path) -> SweepSpec:
    path = Path(path)
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    spec_dir = path.resolve().parent
    levers_raw = raw.get("levers") or {}
    if not levers_raw:
        raise ConfigError(f"{path}: spec has no levers")
    levers = {k: _options(v, spec_dir, f"lever {k!r}") for k, v in levers_raw.items()}
    stress = _options(raw.get("stress") or [{"label": "base", "overlays": []}], spec_dir, "stress")
    return SweepSpec(
        name=str(raw.get("name") or path.stem),
        levers=levers,
        stress=stress,
        mode=str(raw.get("mode", "mc")),
        seed=raw.get("seed", 42),
        paths=raw.get("paths"),
        noise_seeds=int(raw.get("noise_seeds", 0)),
        description=str(raw.get("description") or ""),
        source=path,
        frontier_within=raw.get("frontier_within") or next(iter(levers)),
        fixed=[_resolve_overlay(o, spec_dir) for o in (raw.get("fixed") or [])],
    )


def enumerate_cells(spec: SweepSpec) -> list[Cell]:
    names = list(spec.levers)
    cells = []
    for combo in itertools.product(*(spec.levers[n] for n in names)):
        choices = {n: o.label for n, o in zip(names, combo)}
        overlays = [f for o in combo for f in o.overlays]
        cells.append(Cell("+".join(choices.values()), choices, overlays))
    return cells


# ---------------------------------------------------------------- execution

def _run_job(job: dict) -> dict:
    """Top-level so ProcessPoolExecutor can pickle it (Windows spawn)."""
    from finplan.api import run_scenario

    t0 = time.time()
    # Cells already fan out across the pool; don't nest a second pool per cell.
    res = run_scenario(job["files"], mode=job["mode"], seed=job["seed"], n_paths=job["paths"],
                       workers=1)
    m = res.metrics()
    return {
        "cell": job["cell"],
        **job["choices"],
        "stress": job["stress"],
        "seed": job["seed"],
        "success": round(100 * m["success_probability"], 2),
        "median_terminal": m["terminal_wealth_real_median"],
        "p10_terminal": m["terminal_wealth_real_p10"],
        "lifetime_tax": m["median_lifetime_tax"],
        "first_failure": m["median_first_failure_year"],
        "seconds": round(time.time() - t0, 1),
    }


def _jobs(base_files: list[str], spec: SweepSpec, cells: list[Cell], stress: list[Option],
          seeds: list[int | None]) -> list[dict]:
    jobs = []
    for cell in cells:
        for st in stress:
            for seed in seeds:
                jobs.append({
                    "cell": cell.cell_id, "choices": cell.choices, "stress": st.label,
                    "files": list(base_files) + list(spec.fixed) + cell.overlays + st.overlays,
                    "mode": spec.mode, "seed": seed, "paths": spec.paths,
                })
    return jobs


def _execute(jobs: list[dict], workers: int, progress=None) -> pd.DataFrame:
    rows = []
    if workers <= 1:
        for i, job in enumerate(jobs, 1):
            rows.append(_run_job(job))
            if progress:
                progress(i, len(jobs))
    else:
        with ProcessPoolExecutor(max_workers=workers) as pool:
            futures = [pool.submit(_run_job, j) for j in jobs]
            for i, fut in enumerate(as_completed(futures), 1):
                rows.append(fut.result())
                if progress:
                    progress(i, len(jobs))
    return pd.DataFrame(rows)


# ---------------------------------------------------------------- analysis

def summarize(long: pd.DataFrame, lever_names: list[str], stress_labels: list[str]) -> pd.DataFrame:
    """One row per cell: success under every stress condition, worst case, spread, and
    the reference-condition estate/tax columns."""
    ref = stress_labels[0]
    succ = long.pivot_table(index="cell", columns="stress", values="success", aggfunc="first")
    succ = succ[stress_labels].add_prefix("success_")
    refrows = long[long["stress"] == ref].set_index("cell")
    keep = lever_names + ["median_terminal", "p10_terminal", "lifetime_tax", "first_failure"]
    out = refrows[keep].join(succ)
    scols = [f"success_{s}" for s in stress_labels]
    out["worst_success"] = out[scols].min(axis=1)
    out["worst_stress"] = out[scols].idxmin(axis=1).str.replace("success_", "", regex=False)
    out["success_spread"] = out[scols].max(axis=1) - out[scols].min(axis=1)
    return out.sort_values(["worst_success", "median_terminal"], ascending=False)


def pareto_mask(df: pd.DataFrame, maximize: list[str]) -> pd.Series:
    """True for rows not dominated on all `maximize` columns (ties are not dominance)."""
    vals = df[maximize].to_numpy()
    n = len(vals)
    keep = [True] * n
    for i in range(n):
        for j in range(n):
            if i == j:
                continue
            if (vals[j] >= vals[i]).all() and (vals[j] > vals[i]).any():
                keep[i] = False
                break
    return pd.Series(keep, index=df.index)


def main_effects(summary: pd.DataFrame, lever_names: list[str], ref: str) -> pd.DataFrame:
    """Average outcome by option for each lever (all other levers averaged out)."""
    rows = []
    for lever in lever_names:
        g = summary.groupby(lever)
        agg = pd.DataFrame({
            "worst_success": g["worst_success"].mean(),
            f"success_{ref}": g[f"success_{ref}"].mean(),
            "median_terminal": g["median_terminal"].mean(),
            "lifetime_tax": g["lifetime_tax"].mean(),
            "cells": g.size(),
        })
        for opt, r in agg.iterrows():
            rows.append({"lever": lever, "option": opt, **r.to_dict()})
    me = pd.DataFrame(rows).set_index(["lever", "option"])
    # delta vs the lever's best option, so "what does choosing this cost" reads directly
    best = me.groupby(level=0)["worst_success"].transform("max")
    me["worst_success_vs_best"] = me["worst_success"] - best
    return me.round(2)


def conditional_frontier(summary: pd.DataFrame, within: str, maximize: list[str]) -> pd.Series:
    """Pareto mask computed separately inside each option of lever `within`.

    The global frontier is usually captured by the lever that trades effort for money
    (retire later, spend less) — the trivial answer. Conditioning on that lever shows
    the real choice set at each of its values."""
    mask = pd.Series(False, index=summary.index)
    for _, g in summary.groupby(within):
        mask.loc[g.index] = pareto_mask(g, maximize)
    return mask


def lookup_table(summary: pd.DataFrame, within: str, stress_labels: list[str]) -> pd.DataFrame:
    """Best cell (by worst-case success, then median terminal) per option of `within`,
    with its success under every stress condition. Reads as: 'if the world turns out
    like <stress>, this is the success I get at <option>'."""
    best = (summary.sort_values(["worst_success", "median_terminal"], ascending=False)
            .groupby(within).head(1))
    cols = [f"success_{s}" for s in stress_labels]
    out = best.set_index(within)[cols + ["worst_success", "median_terminal", "lifetime_tax"]]
    out.insert(0, "cell", best.set_index(within).index.map(
        dict(zip(best[within], best.index))))
    return out.sort_values("worst_success", ascending=False)


def noise_table(noise_long: pd.DataFrame) -> pd.DataFrame:
    g = noise_long.groupby("cell")
    return pd.DataFrame({
        "seeds": g["seed"].nunique(),
        "success_min": g["success"].min(),
        "success_max": g["success"].max(),
        "success_range": g["success"].max() - g["success"].min(),
        "success_std": g["success"].std().round(2),
        "median_terminal_range": g["median_terminal"].max() - g["median_terminal"].min(),
    })


# ---------------------------------------------------------------- orchestration

def run_sweep(base_files: list[str], spec: SweepSpec, out_dir: str | Path,
              workers: int | None = None, progress=None,
              frontier_axes: tuple[str, str] = ("worst_success", "median_terminal")) -> dict:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    cells = enumerate_cells(spec)
    lever_names = list(spec.levers)
    stress_labels = [s.label for s in spec.stress]
    jobs = _jobs(base_files, spec, cells, spec.stress, [spec.seed])
    if workers is None:
        workers = max(1, min(len(jobs), (os.cpu_count() or 2) - 2))

    t0 = time.time()
    long = _execute(jobs, workers, progress)
    long.to_csv(out / "cells.csv", index=False)

    within = spec.frontier_within or lever_names[0]
    if within not in lever_names:
        raise ConfigError(f"frontier_within {within!r} is not a lever ({lever_names})")
    summary = summarize(long, lever_names, stress_labels)
    axes = list(frontier_axes)
    summary["frontier"] = pareto_mask(summary, axes)
    summary["frontier_within"] = conditional_frontier(summary, within, axes)
    summary.to_csv(out / "summary.csv")
    frontier = summary[summary["frontier"]].sort_values(frontier_axes[0], ascending=False)
    frontier.to_csv(out / "frontier.csv")
    cond = (summary[summary["frontier_within"]]
            .sort_values([within, frontier_axes[0]], ascending=[True, False]))
    cond.to_csv(out / f"frontier_by_{within}.csv")
    lookup = lookup_table(summary, within, stress_labels)
    lookup.to_csv(out / f"lookup_by_{within}.csv")
    effects = main_effects(summary, lever_names, stress_labels[0])
    effects.to_csv(out / "main_effects.csv")

    noise = None
    if spec.noise_seeds and spec.mode == "mc" and spec.seed is not None:
        top = frontier.head(3).index.tolist()
        cell_by_id = {c.cell_id: c for c in cells}
        seeds = [spec.seed + k for k in range(1, spec.noise_seeds + 1)]
        njobs = _jobs(base_files, spec, [cell_by_id[c] for c in top], spec.stress[:1], seeds)
        nlong = _execute(njobs, min(workers, len(njobs)), progress)
        ref_rows = long[(long["cell"].isin(top)) & (long["stress"] == stress_labels[0])]
        noise = noise_table(pd.concat([ref_rows, nlong], ignore_index=True))
        noise.to_csv(out / "noise.csv")

    meta = {
        "spec": str(spec.source), "name": spec.name, "mode": spec.mode, "seed": spec.seed,
        "paths": spec.paths, "cells": len(cells), "stress": stress_labels,
        "runs": len(long), "workers": workers, "seconds": round(time.time() - t0, 1),
        "frontier_axes": list(frontier_axes), "frontier_within": within,
        "base_files": list(base_files), "fixed": [Path(f).stem for f in spec.fixed],
    }
    (out / "sweep.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    if spec.source:
        (out / "spec.yaml").write_text(Path(spec.source).read_text(encoding="utf-8"), encoding="utf-8")
    return {"long": long, "summary": summary, "frontier": frontier, "frontier_within": cond,
            "lookup": lookup, "within": within, "effects": effects, "noise": noise, "meta": meta}
