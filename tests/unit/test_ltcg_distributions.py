"""Fund capital-gain distributions (`ltcg_distributions` yield category).

Actively managed funds distribute realized gains annually: taxed as LTCG in the year
recognized, reinvested with a basis step-up — so total gain over a full liquidation is
unchanged, it's just recognized earlier (the real-world tax drag vs index funds).
"""

import pytest

from finplan.config.schema import ScenarioConfig
from finplan.engine.runner import run


def _cfg(yields, taxes, wages=0.0, spending=0.0, horizon=2030, basis=600_000):
    d = {
        "sim": {"start_year": 2030, "horizon": horizon},
        "household": {"filing_status": "mfj", "people": [
            {"name": "a", "birth_year": 1980}, {"name": "b", "birth_year": 1980}]},
        "accounts": [
            {"id": "cash", "type": "cash", "balance": 500_000},
            {"id": "funds", "type": "taxable", "balance": 1_000_000,
             "cost_basis": basis, "yields": yields},
        ],
        "income": ([{"id": "job", "owner": "a", "annual": wages,
                     "start": 2030, "end": 2035}] if wages else []),
        "expenses": ([{"id": "living", "annual": spending, "start": 2030,
                       "end": 2035}] if spending else []),
        "policies": {"withdrawal": {"order": ["cash", "taxable"]}},
        "market": {"deterministic": {
            "real_returns": {"stocks": 0.0, "bonds": 0.0, "cash": 0.0},
            "inflation": 0.0}},
        "taxes": taxes,
    }
    return ScenarioConfig.model_validate(d)


REAL_TAX = {"regime": "us_federal", "state": "michigan"}


def test_distribution_recognized_as_ltcg():
    led = run(_cfg({"ltcg_distributions": 0.05}, REAL_TAX, wages=300_000),
              mode="det").ledger.iloc[0]
    assert led["realized_ltcg"] == pytest.approx(50_000)
    assert led["interest_dividends"] == pytest.approx(0.0)  # not ordinary income


def test_distribution_taxed_at_ltcg_plus_niit_plus_mi():
    base = run(_cfg({}, REAL_TAX, wages=300_000), mode="det").ledger.iloc[0]
    with_d = run(_cfg({"ltcg_distributions": 0.05}, REAL_TAX, wages=300_000),
                 mode="det").ledger.iloc[0]
    # at $300k wages, MFJ: 15% LTCG bracket + 3.8% NIIT + 4.25% MI on all $50k
    marginal = (with_d["tax_total"] - base["tax_total"]) / 50_000
    assert marginal == pytest.approx(0.15 + 0.038 + 0.0425, abs=0.005)


def test_full_liquidation_realizes_same_total_gain():
    # 2030: 5% distribution steps basis up; 2031: spending drains the whole account.
    # Distributions shift recognition earlier but cannot change the lifetime total.
    taxes = {"regime": "flat_stub", "flat_effective_rate": 0.0}
    kw = dict(wages=0.0, spending=760_000, horizon=2031, basis=600_000)
    control = run(_cfg({}, taxes, **kw), mode="det").ledger
    with_d = run(_cfg({"ltcg_distributions": 0.05}, taxes, **kw), mode="det").ledger
    assert with_d.iloc[1]["bal_funds"] == pytest.approx(0.0, abs=1.0)
    assert control.iloc[1]["bal_funds"] == pytest.approx(0.0, abs=1.0)
    assert with_d["realized_ltcg"].sum() == pytest.approx(
        control["realized_ltcg"].sum(), abs=1.0)          # == the 400k embedded gain
    assert with_d.iloc[0]["realized_ltcg"] > control.iloc[0]["realized_ltcg"]  # earlier
