"""Simulator plumbing for the 2026-09-12 tax refinements: capital-loss carryforward
threads through per-path state; dependents age off the Michigan return; REIT and
foreign-tax yield categories reach the tax input. Engine arithmetic itself is
golden-tested in tests/golden/tax_cases/."""

from finplan.config.schema import DependentCfg, ScenarioConfig
from finplan.engine.runner import run

BASE = {
    "sim": {"start_year": 2030, "horizon": 2034},
    "household": {
        "filing_status": "mfj",
        "people": [{"name": "sam", "birth_year": 1980, "life_expectancy_age": 90},
                   {"name": "kim", "birth_year": 1982, "life_expectancy_age": 90}],
    },
    "accounts": [
        {"id": "cash", "type": "cash", "balance": 10_000},
        # embedded LOSS: every sale realizes a capital loss (average-cost basis)
        {"id": "brokerage", "type": "taxable", "balance": 400_000, "cost_basis": 800_000,
         "allocation": {"stocks": 0.0, "bonds": 0.0, "cash": 1.0}},
    ],
    "income": [{"id": "salary", "owner": "sam", "annual": 120_000, "start": 2030,
                "end": 2034}],
    "expenses": [{"id": "living", "annual": 150_000, "start": 2030, "end": 2034}],
    "policies": {"withdrawal": {"order": ["cash", "taxable"]}},
    "market": {"deterministic": {"real_returns": {"stocks": 0.0, "bonds": 0.0, "cash": 0.0},
                                 "inflation": 0.0}},
    "taxes": {"regime": "us_federal", "state": "michigan"},
}


def _ledger(extra=None):
    cfg = dict(BASE)
    if extra:
        cfg = {**cfg, **extra}
    return run(ScenarioConfig.model_validate(cfg), mode="det").ledger.set_index("year")


def test_capital_loss_carryforward_accumulates_and_offsets_3000_per_year():
    L = _ledger()
    # each year's sale realizes roughly half its amount as a loss; only $3k offsets
    # ordinary income, the rest carries and grows year over year
    cf = L["capital_loss_carryforward"]
    assert cf.loc[2030] > 0
    assert all(cf.loc[y] > cf.loc[y - 1] for y in range(2031, 2035))
    # the $3,000 offset shows up as AGI = wages - 3,000 (no other income modeled)
    assert abs(L.loc[2031, "agi"] - (120_000 - 3_000)) < 1.0


def test_carryforward_is_consumed_by_a_later_gain_year():
    from finplan.model.household import FilingStatus
    from finplan.taxes.engine import compute_year_tax
    from finplan.taxes.params import load_federal
    from finplan.taxes.types import TaxInput

    params = load_federal(2026)
    y1 = compute_year_tax(TaxInput(year=2026, filing_status=FilingStatus.MFJ,
                                   ages={"a": 50, "b": 50}, wages=100_000,
                                   realized_ltcg=-20_000), params)
    assert y1.capital_loss_carryforward_out == 17_000
    y2 = compute_year_tax(TaxInput(year=2026, filing_status=FilingStatus.MFJ,
                                   ages={"a": 51, "b": 51}, wages=100_000,
                                   realized_ltcg=25_000,
                                   capital_loss_carryforward=y1.capital_loss_carryforward_out),
                          params)
    assert y2.capital_loss_carryforward_out == 0
    assert abs(y2.agi - 108_000) < 1.0     # 25,000 - 17,000 of gain survives


def test_dependents_age_off_michigan_exemptions():
    kid = {"name": "jo", "birth_year": 2012}          # claimable through age 18 -> 2030
    with_kid = _ledger({"household": {**BASE["household"], "dependents": [kid]}})
    without = _ledger()
    # 2030: kid is 18 -> one extra $5,900 exemption (2026 params, 0% inflation)
    assert abs((without.loc[2030, "tax_state"] - with_kid.loc[2030, "tax_state"])
               - 0.0425 * 5_900) < 1.0
    # 2031: kid is 19 -> no difference
    assert abs(without.loc[2031, "tax_state"] - with_kid.loc[2031, "tax_state"]) < 1.0
    assert DependentCfg(name="x", birth_year=2012).claimable_in(2030)
    assert not DependentCfg(name="x", birth_year=2012).claimable_in(2031)


def test_reit_and_foreign_tax_yields_reach_the_tax_engine():
    acct = {"id": "brokerage", "type": "taxable", "balance": 1_000_000,
            "cost_basis": 1_000_000, "allocation": {"stocks": 0.0, "bonds": 0.0, "cash": 1.0},
            "yields": {"sec199a_dividends": 0.001, "foreign_tax": 0.0001}}
    base = {**BASE, "accounts": [BASE["accounts"][0], acct],
            "expenses": [{"id": "living", "annual": 50_000, "start": 2030, "end": 2034}],
            "taxes": {"regime": "us_federal", "state": "michigan", "qbi_wage_cap": 0.0}}
    L = _ledger(base)
    # $100 of foreign tax paid credits in full (de minimis election)
    assert abs(L.loc[2030, "foreign_tax_credit"] - 100.0) < 0.01
    # $1,000 of REIT dividends count as ordinary income (interest_dividends) ...
    assert abs(L.loc[2030, "interest_dividends"] - 1_000.0) < 0.01
    # ... and earn the 20% QBI deduction even with no business income
    assert abs(L.loc[2030, "taxable_income"]
               - (120_000 + 1_000 - 32_200 - 200)) < 1.0


def test_state_tax_addback_reaches_michigan():
    inc = [{"id": "scorp", "owner": "sam", "annual": 100_000, "start": 2030, "end": 2034,
            "kind": "business", "fica": False, "state_tax_addback": 0.05}]
    with_ab = _ledger({"income": inc})
    inc0 = [{**inc[0], "state_tax_addback": 0.0}]
    without = _ledger({"income": inc0})
    assert abs((with_ab.loc[2030, "tax_state"] - without.loc[2030, "tax_state"])
               - 0.0425 * 5_000) < 1.0
