"""Sweep: cell enumeration, overlay stacking order, summary/frontier maths, and an
end-to-end deterministic run on a tiny synthetic household (no personal data)."""

from pathlib import Path

import pandas as pd
import pytest
import yaml

from finplan.config.loader import ConfigError
from finplan.sweep import (
    conditional_frontier,
    enumerate_cells,
    load_spec,
    lookup_table,
    main_effects,
    pareto_mask,
    run_sweep,
    summarize,
)

BASE = {
    "meta": {"name": "toy", "description": "toy"},
    "sim": {"start_year": 2030, "horizon": 2039},
    "household": {
        "filing_status": "single",
        "people": [{"name": "sam", "birth_year": 1980, "retirement_age": 52,
                    "life_expectancy_age": 90}],
    },
    "accounts": [
        {"id": "cash", "type": "cash", "balance": 100_000},
        {"id": "brokerage", "type": "taxable", "balance": 400_000, "cost_basis": 400_000},
    ],
    "income": [{"id": "salary", "owner": "sam", "annual": 100_000, "start": 2030,
                "end": "retirement"}],
    "expenses": [{"id": "living", "annual": 60_000, "start": 2030, "end": 2039}],
    "policies": {"withdrawal": {"order": ["cash", "taxable"]}},
    "market": {"deterministic": {"real_returns": {"stocks": 0.0, "bonds": 0.0, "cash": 0.0},
                                 "inflation": 0.0}},
    "taxes": {"regime": "flat_stub", "flat_effective_rate": 0.20},
}


def _write(tmp: Path, rel: str, data: dict) -> Path:
    p = tmp / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    return p


@pytest.fixture
def workspace(tmp_path: Path) -> dict:
    base = _write(tmp_path, "scenarios/base.yaml", BASE)
    _write(tmp_path, "scenarios/overlays/retire_54.yaml",
           {"meta": {"name": "retire_54", "description": "x"},
            "household": {"people": [{"name": "sam", "retirement_age": 54}]}})
    _write(tmp_path, "scenarios/overlays/spend_plus10.yaml",
           {"meta": {"name": "spend_plus10", "description": "x"},
            "expenses": [{"id": "living", "annual": 70_000}]})
    spec = _write(tmp_path, "scenarios/sweeps/grid.yaml", {
        "name": "grid", "mode": "det", "seed": None,
        "levers": {
            "retire": [{"label": "r52", "overlays": []},
                       {"label": "r54", "overlays": ["retire_54"]}],
        },
        "stress": [{"label": "base", "overlays": []},
                   {"label": "spend10", "overlays": ["spend_plus10"]}],
    })
    return {"base": base, "spec": spec, "root": tmp_path}


def test_load_spec_resolves_overlays_and_enumerates_cells(workspace):
    spec = load_spec(workspace["spec"])
    cells = enumerate_cells(spec)
    assert [c.cell_id for c in cells] == ["r52", "r54"]
    assert cells[1].overlays[0].endswith("retire_54.yaml")
    assert [s.label for s in spec.stress] == ["base", "spend10"]
    assert spec.fixed == [] and spec.frontier_within == "retire"


def test_fixed_overlays_sit_between_base_and_cell(workspace):
    from finplan.sweep import _jobs

    root = workspace["root"]
    spec_path = _write(root, "scenarios/sweeps/fixed.yaml", {
        "name": "fixed", "mode": "det", "fixed": ["spend_plus10"],
        "levers": {"retire": [{"label": "r54", "overlays": ["retire_54"]}]},
    })
    spec = load_spec(spec_path)
    assert spec.fixed[0].endswith("spend_plus10.yaml")
    job = _jobs(["base.yaml"], spec, enumerate_cells(spec), spec.stress, [None])[0]
    assert [Path(f).name for f in job["files"]] == ["base.yaml", "spend_plus10.yaml", "retire_54.yaml"]


def test_load_spec_rejects_unknown_overlay(tmp_path):
    spec = _write(tmp_path, "scenarios/sweeps/bad.yaml",
                  {"levers": {"x": [{"label": "a", "overlays": ["nope"]}]}})
    with pytest.raises(ConfigError, match="nope"):
        load_spec(spec)


def test_pareto_mask_keeps_only_undominated():
    df = pd.DataFrame({"a": [1, 2, 2, 3], "b": [9, 8, 7, 1]})
    # (1,9) undominated; (2,8) undominated; (2,7) dominated by (2,8); (3,1) undominated
    assert pareto_mask(df, ["a", "b"]).tolist() == [True, True, False, True]


def test_summarize_and_main_effects_shapes():
    long = pd.DataFrame([
        {"cell": "a+x", "L1": "a", "L2": "x", "stress": "base", "success": 90.0,
         "median_terminal": 100, "p10_terminal": 10, "lifetime_tax": 5, "first_failure": None},
        {"cell": "a+x", "L1": "a", "L2": "x", "stress": "s1", "success": 80.0,
         "median_terminal": 90, "p10_terminal": 1, "lifetime_tax": 5, "first_failure": 2050},
        {"cell": "b+x", "L1": "b", "L2": "x", "stress": "base", "success": 95.0,
         "median_terminal": 120, "p10_terminal": 20, "lifetime_tax": 6, "first_failure": None},
        {"cell": "b+x", "L1": "b", "L2": "x", "stress": "s1", "success": 70.0,
         "median_terminal": 80, "p10_terminal": 2, "lifetime_tax": 6, "first_failure": 2045},
    ])
    s = summarize(long, ["L1", "L2"], ["base", "s1"])
    assert s.loc["a+x", "worst_success"] == 80.0 and s.loc["a+x", "worst_stress"] == "s1"
    assert s.loc["b+x", "success_spread"] == 25.0
    # reference-condition estate column comes from the "base" row
    assert s.loc["b+x", "median_terminal"] == 120
    me = main_effects(s, ["L1", "L2"], "base")
    assert me.loc[("L1", "a"), "worst_success_vs_best"] == 0.0
    assert me.loc[("L1", "b"), "worst_success_vs_best"] == -10.0


def test_conditional_frontier_and_lookup():
    # lever R dominates globally (r2 rows beat every r1 row); conditioning on R must
    # still surface the best r1 row, and the lookup gives one row per R option.
    s = pd.DataFrame({
        "R": ["r1", "r1", "r2", "r2"], "L": ["a", "b", "a", "b"],
        "worst_success": [60.0, 65.0, 90.0, 88.0],
        "median_terminal": [100, 90, 200, 250],
        "success_base": [70.0, 72.0, 95.0, 94.0], "success_s1": [60.0, 65.0, 90.0, 88.0],
        "lifetime_tax": [1, 1, 2, 2],
    }, index=["r1+a", "r1+b", "r2+a", "r2+b"])
    glob = pareto_mask(s, ["worst_success", "median_terminal"])
    assert glob.tolist() == [False, False, True, True]
    cond = conditional_frontier(s, "R", ["worst_success", "median_terminal"])
    assert cond.tolist() == [True, True, True, True]     # r1 rows trade off against each other
    lk = lookup_table(s, "R", ["base", "s1"])
    assert list(lk.index) == ["r2", "r1"]                # sorted by worst-case success
    assert lk.loc["r1", "cell"] == "r1+b" and lk.loc["r1", "success_s1"] == 65.0


def test_run_sweep_end_to_end_det(workspace, tmp_path, monkeypatch):
    monkeypatch.chdir(workspace["root"])
    spec = load_spec(workspace["spec"])
    out = tmp_path / "out"
    res = run_sweep([str(workspace["base"])], spec, out, workers=1)
    assert len(res["long"]) == 4                       # 2 cells x 2 stress
    assert set(res["summary"].index) == {"r52", "r54"}
    # working two more years leaves more money in every condition
    assert res["summary"].loc["r54", "median_terminal"] > res["summary"].loc["r52", "median_terminal"]
    for name in ["cells.csv", "summary.csv", "frontier.csv", "main_effects.csv", "sweep.json", "spec.yaml"]:
        assert (out / name).exists()
