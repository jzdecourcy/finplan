"""Guardrail spending policy: discretionary streams cut after down years in retirement."""

import pytest

from finplan.config.schema import ScenarioConfig
from finplan.engine.runner import run

BASE = {
    "sim": {"start_year": 2030, "horizon": 2032},
    "household": {"filing_status": "mfj", "people": [
        {"name": "a", "birth_year": 1970, "retirement_age": 55},
        {"name": "b", "birth_year": 1970, "retirement_age": 55}]},
    "accounts": [{"id": "cash", "type": "cash", "balance": 2_000_000}],
    "income": [],
    "expenses": [
        {"id": "fixed", "annual": 60_000, "start": 2030, "end": 2032},
        {"id": "flex", "annual": 40_000, "start": 2030, "end": 2032,
         "discretionary": True},
    ],
    "market": {"deterministic": {
        "real_returns": {"stocks": -0.10, "bonds": 0.0, "cash": 0.0},
        "inflation": 0.0}},
    "taxes": {"regime": "flat_stub", "flat_effective_rate": 0.0},
}


def _run(policy):
    cfg = dict(BASE, policies={"spending": policy,
                               "withdrawal": {"order": ["cash"]}})
    return run(ScenarioConfig.model_validate(cfg), mode="det").ledger.set_index("year")


def test_guardrail_cuts_discretionary_after_down_year():
    led = _run({"type": "guardrail", "cut_fraction": 0.5})
    assert led.loc[2030, "spending"] == pytest.approx(100_000)  # no prior year yet
    # stocks returned -10% real in 2030 -> 2031 discretionary halved
    assert led.loc[2031, "spending"] == pytest.approx(60_000 + 20_000)
    assert led.loc[2032, "spending"] == pytest.approx(80_000)


def test_fixed_real_never_cuts():
    led = _run({"type": "fixed_real"})
    for y in (2030, 2031, 2032):
        assert led.loc[y, "spending"] == pytest.approx(100_000)


def test_guardrail_inactive_while_working():
    cfg = dict(BASE)
    cfg["income"] = [{"id": "sal", "owner": "a", "annual": 200_000,
                      "start": 2030, "end": 2032}]
    cfg["policies"] = {"spending": {"type": "guardrail", "cut_fraction": 0.5},
                       "withdrawal": {"order": ["cash"]}}
    led = run(ScenarioConfig.model_validate(cfg), mode="det").ledger.set_index("year")
    for y in (2030, 2031, 2032):
        assert led.loc[y, "spending"] == pytest.approx(100_000)
