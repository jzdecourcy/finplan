"""Tax character of investment yield: Treasury interest (MI-exempt), muni interest
(federal-exempt, MI addback, SS provisional income), cash interest taxation."""

import pytest

from finplan.model.household import FilingStatus
from finplan.taxes.engine import compute_year_tax
from finplan.taxes.params import load_federal, load_michigan
from finplan.taxes.types import TaxInput

FED = load_federal(2026)
MI = load_michigan(2026)


def _inp(**kw):
    kw.setdefault("year", 2026)
    kw.setdefault("filing_status", FilingStatus.MFJ)
    kw.setdefault("ages", {"a": 49, "b": 51})
    return TaxInput(**kw)


def test_treasury_interest_federal_taxable_mi_exempt():
    base = compute_year_tax(_inp(wages=200_000), FED, MI)
    with_tsy = compute_year_tax(_inp(wages=200_000, us_gov_interest=10_000), FED, MI)
    assert with_tsy.federal > base.federal          # federally taxable
    assert with_tsy.state == pytest.approx(base.state)  # Michigan exempt


def test_regular_interest_taxed_by_both():
    base = compute_year_tax(_inp(wages=200_000), FED, MI)
    with_int = compute_year_tax(_inp(wages=200_000, interest=10_000), FED, MI)
    assert with_int.federal > base.federal
    assert with_int.state == pytest.approx(base.state + 0.0425 * 10_000)


def test_muni_interest_federal_exempt_mi_addback():
    base = compute_year_tax(_inp(wages=200_000), FED, MI)
    with_muni = compute_year_tax(_inp(wages=200_000, tax_exempt_interest=10_000), FED, MI)
    assert with_muni.federal == pytest.approx(base.federal)  # federal exempt
    assert with_muni.agi == pytest.approx(base.agi)
    assert with_muni.state == pytest.approx(base.state + 0.0425 * 10_000)  # MI addback


def test_muni_interest_counts_in_ss_provisional_income():
    # retiree at the 50% phase-in edge: muni interest drags SS into taxability
    quiet = compute_year_tax(_inp(ss_benefits=40_000, other_ordinary=25_000), FED, None)
    with_muni = compute_year_tax(
        _inp(ss_benefits=40_000, other_ordinary=25_000, tax_exempt_interest=15_000),
        FED, None,
    )
    assert with_muni.taxable_ss > quiet.taxable_ss


def test_treasury_interest_hits_niit():
    inp_hi = _inp(wages=300_000, us_gov_interest=20_000)
    r = compute_year_tax(inp_hi, FED, None)
    base = compute_year_tax(_inp(wages=300_000), FED, None)
    # marginal federal on the treasury interest should include the 3.8% NIIT
    marginal = (r.federal - base.federal) / 20_000
    assert marginal > 0.24 + 0.037  # 24% bracket + NIIT


def test_simulator_taxes_cash_and_yield():
    from finplan.config.schema import ScenarioConfig
    from finplan.engine.runner import run

    cfg = ScenarioConfig.model_validate({
        "sim": {"start_year": 2030, "horizon": 2031},
        "household": {"filing_status": "mfj", "people": [
            {"name": "a", "birth_year": 1980}, {"name": "b", "birth_year": 1980}]},
        "accounts": [
            {"id": "hysa", "type": "cash", "balance": 100_000},
            {"id": "tsy", "type": "taxable", "balance": 200_000,
             "yields": {"us_gov_interest": 0.04}},
        ],
        "income": [],
        "expenses": [{"id": "living", "annual": 10_000, "start": 2030, "end": 2031}],
        "market": {"deterministic": {
            "real_returns": {"stocks": 0.0, "bonds": 0.0, "cash": 0.03},
            "inflation": 0.0}},
        "taxes": {"regime": "us_federal", "state": "michigan"},
    })
    led = run(cfg, mode="det").ledger.iloc[0]
    # cash 100k x 3% + treasury 200k x 4% = 11,000 of interest income recognized
    assert led["interest_dividends"] == pytest.approx(3_000 + 8_000)
    # under the MFJ standard deduction -> no federal; MI taxes nothing:
    # treasury interest exempt, and cash interest < exemptions
    assert led["agi"] == pytest.approx(11_000)
    assert led["tax_total"] == pytest.approx(0.0, abs=1.0)
