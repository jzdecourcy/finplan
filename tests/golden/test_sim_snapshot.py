"""Full-lifetime deterministic ledger pinned as a golden CSV.

Any change to the simulation's behavior — ordering, tax math, policy logic — shows up as
a diff here and must be intentionally re-blessed with `pytest --update-golden`.

The scenario is fixed HERE (not scenarios/base.yaml, which the user customizes): MFJ
Michigan household exercising salaries, 401k max deferral + match, RMDs at 75,
fill-to-12%-bracket conversions in early retirement, SS claiming, 529 college draws,
a house-purchase event, and taxable/traditional/roth/hsa/529 withdrawals.
"""

from pathlib import Path

import pandas as pd
import pytest

from finplan.config.schema import ScenarioConfig
from finplan.engine.runner import run

SNAPSHOT = Path(__file__).parent / "sim_snapshots" / "lifetime_det.csv"

SCENARIO = {
    "meta": {"name": "golden-lifetime"},
    "sim": {"start_year": 2026, "horizon": 2075},
    "household": {
        "filing_status": "mfj",
        "people": [
            {"name": "a", "birth_year": 1980, "retirement_age": 60, "ss_claim_age": 67,
             "ss_pia_monthly": 3000, "life_expectancy_age": 95},
            {"name": "b", "birth_year": 1982, "retirement_age": 60, "ss_claim_age": 70,
             "ss_pia_monthly": 2000, "life_expectancy_age": 95},
        ],
    },
    "accounts": [
        {"id": "brokerage", "type": "taxable", "owner": "a", "balance": 400_000,
         "cost_basis": 250_000, "allocation": {"stocks": 0.8, "bonds": 0.2}},
        {"id": "401k-a", "type": "traditional", "owner": "a", "balance": 500_000,
         "allocation": {"stocks": 0.7, "bonds": 0.3}},
        {"id": "roth-a", "type": "roth", "owner": "a", "balance": 100_000,
         "cost_basis": 80_000, "allocation": {"stocks": 0.9, "bonds": 0.1}},
        {"id": "hsa-a", "type": "hsa", "owner": "a", "balance": 30_000,
         "allocation": {"stocks": 0.8, "bonds": 0.2}},
        {"id": "529-kid", "type": "529", "owner": "a", "beneficiary": "kid",
         "balance": 60_000, "allocation": {"stocks": 0.6, "bonds": 0.4}},
        {"id": "cash", "type": "cash", "balance": 40_000},
    ],
    "income": [
        {"id": "sal-a", "owner": "a", "annual": 160_000, "start": 2026, "end": "retirement"},
        {"id": "sal-b", "owner": "b", "annual": 90_000, "start": 2026, "end": "retirement"},
    ],
    "expenses": [
        {"id": "living", "annual": 100_000, "start": 2026, "end": "death"},
        {"id": "college", "annual": 35_000, "start": 2033, "end": 2036, "education": True},
    ],
    "events": [
        {"id": "house", "year": 2028, "cash": -150_000},
    ],
    "policies": {
        "withdrawal": {"order": ["cash", "taxable", "traditional", "roth", "hsa"]},
        "contribution": {
            "pretax": [{"account": "401k-a"}],
            "match_pct": {"401k-a": 0.04},
            "priority": ["taxable"],
        },
        "roth_conversion": {"type": "fill_bracket", "bracket_top": 0.12,
                            "start": "retirement", "end": "age:a:74"},
    },
    "market": {
        "deterministic": {
            "real_returns": {"stocks": 0.05, "bonds": 0.015, "cash": 0.0},
            "inflation": 0.025,
        }
    },
    "taxes": {"regime": "us_federal", "state": "michigan", "base_params_year": 2026},
}


def test_lifetime_ledger_matches_snapshot(request):
    cfg = ScenarioConfig.model_validate(SCENARIO)
    ledger = run(cfg, mode="det").ledger.drop(columns=["path"]).round(2)
    if request.config.getoption("--update-golden") or not SNAPSHOT.exists():
        SNAPSHOT.parent.mkdir(parents=True, exist_ok=True)
        ledger.to_csv(SNAPSHOT, index=False)
        if not request.config.getoption("--update-golden"):
            pytest.fail(f"snapshot created at {SNAPSHOT}; rerun to verify")
        return
    expected = pd.read_csv(SNAPSHOT)
    pd.testing.assert_frame_equal(
        ledger.reset_index(drop=True), expected, check_dtype=False,
        check_exact=False, atol=0.05,
    )


def test_lifetime_run_is_sane():
    cfg = ScenarioConfig.model_validate(SCENARIO)
    results = run(cfg, mode="det")
    df = results.ledger.set_index("year")
    assert results.success_probability == 1.0
    # conversions happen only in the window (2042 retirement -> 2054)
    conv_years = df[df["roth_conversion"] > 0].index
    assert conv_years.min() >= 2042 and conv_years.max() <= 2054
    # RMDs start at 75 for born-1980 (age 75 in 2055)
    rmd_years = df[df["rmd"] > 0].index
    assert rmd_years.min() == 2055
    # college years draw the 529 down
    assert df.loc[2037, "bal_529-kid"] < df.loc[2032, "bal_529-kid"]
