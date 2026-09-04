"""Hand-computed 5-year scenario asserted to the dollar.

Setup: one person, zero inflation, zero returns, flat 20% tax + 7.65% FICA on wages.
Salary 100k for 2030-2031; living expenses 50k for all 5 years; cash 100k;
taxable 100k with basis == balance (so withdrawals realize no gains -> zero tax).

By hand:
  2030  wages 100k, tax 27,650, surplus 22,350 -> taxable. NW = 222,350
  2031  same.                                     NW = 244,700
  2032  withdraw 50k from cash (tax-free).        NW = 194,700
  2033  withdraw 50k from cash (exhausts it).     NW = 144,700
  2034  withdraw 50k from taxable (no gain).      NW =  94,700
"""

import pytest

from finplan.config.schema import ScenarioConfig
from finplan.engine.runner import run

CONFIG = {
    "sim": {"start_year": 2030, "horizon": 2034},
    "household": {
        "filing_status": "single",
        "people": [{"name": "sam", "birth_year": 1980, "life_expectancy_age": 90}],
    },
    "accounts": [
        {"id": "cash", "type": "cash", "balance": 100_000},
        {"id": "brokerage", "type": "taxable", "balance": 100_000, "cost_basis": 100_000},
    ],
    "income": [
        {"id": "salary", "owner": "sam", "annual": 100_000, "start": 2030, "end": 2031}
    ],
    "expenses": [{"id": "living", "annual": 50_000, "start": 2030, "end": 2034}],
    "policies": {"withdrawal": {"order": ["cash", "taxable"]}},
    "market": {
        "deterministic": {
            "real_returns": {"stocks": 0.0, "bonds": 0.0, "cash": 0.0},
            "inflation": 0.0,
        }
    },
    "taxes": {"regime": "flat_stub", "flat_effective_rate": 0.20},
}


@pytest.fixture(scope="module")
def ledger():
    cfg = ScenarioConfig.model_validate(CONFIG)
    return run(cfg, mode="det").ledger.set_index("year")


def test_working_years(ledger):
    for year in (2030, 2031):
        row = ledger.loc[year]
        assert row["wages"] == 100_000
        assert row["tax_total"] == pytest.approx(27_650)
        assert row["contributions_total"] == pytest.approx(22_350)
        assert row["withdrawals_total"] == 0


def test_net_worth_trajectory(ledger):
    expected = {2030: 222_350, 2031: 244_700, 2032: 194_700, 2033: 144_700, 2034: 94_700}
    for year, nw in expected.items():
        assert ledger.loc[year, "net_worth"] == pytest.approx(nw, abs=1.5)


def test_retirement_years_tax_free(ledger):
    for year in (2032, 2033, 2034):
        row = ledger.loc[year]
        assert row["tax_total"] == pytest.approx(0, abs=0.5)
        assert row["withdrawals_total"] == pytest.approx(50_000, abs=1.5)
        assert not row["failed"]


def test_cash_exhausts_then_taxable(ledger):
    assert ledger.loc[2033, "bal_cash"] == pytest.approx(0)
    assert ledger.loc[2034, "bal_brokerage"] == pytest.approx(94_700, abs=1.5)


def test_no_gains_realized_when_basis_equals_balance(ledger):
    assert ledger["realized_ltcg"].sum() == pytest.approx(0)
