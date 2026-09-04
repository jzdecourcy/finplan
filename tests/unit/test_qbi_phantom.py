"""QBI deduction and phantom K-1 income."""

import pytest

from finplan.config.schema import ScenarioConfig
from finplan.engine.runner import run
from finplan.model.household import FilingStatus
from finplan.taxes.engine import compute_year_tax
from finplan.taxes.params import load_federal
from finplan.taxes.types import TaxInput

FED = load_federal(2026)


def _inp(**kw):
    kw.setdefault("year", 2026)
    kw.setdefault("filing_status", FilingStatus.MFJ)
    kw.setdefault("ages", {"a": 49, "b": 51})
    return TaxInput(**kw)


def test_qbi_twenty_percent_when_under_wage_cap():
    # enough other income that 20% x QBI is the binding limit
    r = compute_year_tax(_inp(wages=150_000, business=100_000, qbi_wage_cap=68_000), FED)
    no_qbi = compute_year_tax(_inp(wages=150_000, business=100_000), FED)
    assert no_qbi.taxable_income - r.taxable_income == pytest.approx(20_000)


def test_qbi_income_limit_when_business_is_only_income():
    # s199A caps at 20% of taxable income: (100,000 - 32,200) x 20% = 13,560
    r = compute_year_tax(_inp(business=100_000, qbi_wage_cap=68_000), FED)
    no_qbi = compute_year_tax(_inp(business=100_000), FED)
    assert no_qbi.taxable_income - r.taxable_income == pytest.approx(13_560)


def test_qbi_wage_cap_binds():
    r = compute_year_tax(_inp(business=400_000, qbi_wage_cap=68_000), FED)
    no_qbi = compute_year_tax(_inp(business=400_000), FED)
    assert no_qbi.taxable_income - r.taxable_income == pytest.approx(68_000)


def test_qbi_income_limit_binds_when_taxable_income_small():
    # large business loss elsewhere -> taxable income below QBI base
    r = compute_year_tax(
        _inp(business=100_000, other_ordinary=-60_000, qbi_wage_cap=68_000), FED
    )
    # 20% of taxable-before-QBI (40,000 - 32,200 std = 7,800) = 1,560 < 20,000
    no_qbi = compute_year_tax(_inp(business=100_000, other_ordinary=-60_000), FED)
    assert no_qbi.taxable_income - r.taxable_income == pytest.approx(1_560)


def test_qbi_none_disables():
    r = compute_year_tax(_inp(business=100_000, qbi_wage_cap=None), FED)
    no_qbi = compute_year_tax(_inp(business=100_000), FED)
    assert r.taxable_income == no_qbi.taxable_income


def test_phantom_income_taxed_but_not_spendable():
    cfg = ScenarioConfig.model_validate({
        "sim": {"start_year": 2030, "horizon": 2030},
        "household": {"filing_status": "mfj", "people": [
            {"name": "a", "birth_year": 1980}, {"name": "b", "birth_year": 1980}]},
        "accounts": [{"id": "cash", "type": "cash", "balance": 500_000}],
        "income": [
            {"id": "biz-cash", "owner": "a", "kind": "business", "annual": 100_000,
             "start": 2030, "end": 2030, "fica": False},
            {"id": "biz-phantom", "owner": "a", "kind": "business", "annual": 50_000,
             "start": 2030, "end": 2030, "fica": False, "phantom": True},
        ],
        "expenses": [{"id": "living", "annual": 60_000, "start": 2030, "end": 2030}],
        "market": {"deterministic": {"real_returns": {"stocks": 0, "bonds": 0, "cash": 0},
                                     "inflation": 0}},
        "taxes": {"regime": "us_federal", "state": "none"},
    })
    led = run(cfg, mode="det").ledger.iloc[0]
    # AGI sees all 150k of business income
    assert led["agi"] == pytest.approx(150_000)
    # but cash only received 100k: net worth change = 100k - 60k - tax
    assert led["net_worth"] == pytest.approx(500_000 + 100_000 - 60_000 - led["tax_total"])
