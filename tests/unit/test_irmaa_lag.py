"""IRMAA in the simulator: the surcharge paid in year Y is priced off MAGI from
year Y-2 (seeded from taxes.irmaa.prior_magi before the sim has its own history),
CPI-indexed thresholds and amounts, and it switches off cleanly.

Household: two people already on Medicare (68/66 in 2026), MFJ, spending funded from
a traditional IRA so MAGI runs well above the first joint threshold every year.
"""

import pytest

from finplan.config.schema import ScenarioConfig
from finplan.engine.runner import run
from finplan.taxes.engine import FederalStateTaxEngine
from finplan.taxes.irmaa import irmaa_surcharge


def _cfg(**irmaa):
    return ScenarioConfig.model_validate({
        "meta": {"name": "irmaa-lag"},
        "sim": {"start_year": 2026, "horizon": 2032},
        "household": {
            "filing_status": "mfj",
            "people": [
                {"name": "a", "birth_year": 1958, "retirement_age": 60},
                {"name": "b", "birth_year": 1960, "retirement_age": 60},
            ],
        },
        "accounts": [
            {"id": "ira", "type": "traditional", "owner": "a", "balance": 8_000_000,
             "allocation": {"stocks": 0.5, "bonds": 0.5}},
        ],
        "expenses": [{"id": "living", "annual": 300_000, "start": 2026, "end": "death"}],
        "policies": {"withdrawal": {"order": ["traditional"]}},
        "market": {"deterministic": {
            "real_returns": {"stocks": 0.05, "bonds": 0.015, "cash": 0.0},
            "inflation": 0.025,
        }},
        "taxes": {"regime": "us_federal", "state": "none", "base_params_year": 2026,
                  "irmaa": irmaa},
    })


def _ledger(cfg):
    return run(cfg, mode="det").ledger.set_index("year")


def test_seeded_lookback_prices_first_two_years():
    df = _ledger(_cfg(prior_magi={2024: 250_000, 2025: 100_000}))
    # 2026 uses the 2024 return: tier 1, two enrollees, cpi 1.0 in the start year
    assert df.loc[2026, "irmaa_tier"] == 1
    assert df.loc[2026, "tax_irmaa"] == pytest.approx(2 * 12 * (81.20 + 14.50), abs=0.01)
    # 2027 uses the 2025 return: below the first threshold, nothing owed
    assert df.loc[2027, "irmaa_tier"] == 0
    assert df.loc[2027, "tax_irmaa"] == 0.0
    # the surcharge is inside tax_total, so the withdrawal loop funds it
    assert df.loc[2026, "tax_total"] >= df.loc[2026, "tax_federal"] + df.loc[2026, "tax_irmaa"] - 0.01


def test_simulated_magi_drives_irmaa_two_years_later():
    df = _ledger(_cfg(prior_magi={2024: 250_000, 2025: 100_000}))
    engine = FederalStateTaxEngine(base_year=2026, state="none")
    for year in (2028, 2029, 2030):
        lagged_magi = df.loc[year - 2, "magi_irmaa"]
        params = engine.params_for_year(round(df.loc[year, "cpi_factor"], 3))[0]["irmaa"]
        expect = irmaa_surcharge(lagged_magi, 2, "mfj", params)
        assert expect.tier > 0, "test scenario should sit in a surcharge tier"
        assert df.loc[year, "irmaa_tier"] == expect.tier
        assert df.loc[year, "tax_irmaa"] == pytest.approx(expect.annual_total, abs=0.01)


def test_unseeded_first_years_fall_back_to_own_magi():
    df = _ledger(_cfg())
    # no prior_magi: 2026 is priced off 2026's own MAGI (~300k+ of IRA draws)
    assert df.loc[2026, "irmaa_tier"] > 0
    assert df.loc[2026, "tax_irmaa"] > 0


def test_disabled_or_too_young_pays_nothing():
    assert (_ledger(_cfg(enabled=False))["tax_irmaa"] == 0).all()
    assert (_ledger(_cfg(medicare_age=80))["tax_irmaa"] == 0).all()
