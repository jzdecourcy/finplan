"""Property-style tests of the tax pipeline: structural invariants that must hold for any
parameter values. Value-exact checks live in tests/golden/."""

from __future__ import annotations

import pytest

from finplan.model.household import FilingStatus
from finplan.taxes.engine import compute_year_tax
from finplan.taxes.params import load_federal
from finplan.taxes.types import TaxInput


@pytest.fixture(scope="module")
def params():
    return load_federal(2026)


def _inp(**kw) -> TaxInput:
    kw.setdefault("year", 2026)
    kw.setdefault("filing_status", FilingStatus.MFJ)
    kw.setdefault("ages", {"a": 45, "b": 45})
    return TaxInput(**kw)


def test_tax_monotonic_in_wages(params):
    prev = -1.0
    for wages in range(0, 1_000_001, 50_000):
        t = compute_year_tax(_inp(wages=wages), params).federal
        assert t >= prev
        prev = t


def test_marginal_never_exceeds_top_rate_plus_niit(params):
    top = params["ordinary_brackets"]["mfj"][-1]["rate"] + params["niit"]["rate"]
    for base in range(10_000, 900_000, 37_500):
        t1 = compute_year_tax(_inp(wages=base), params).federal
        t2 = compute_year_tax(_inp(wages=base + 100), params).federal
        assert (t2 - t1) / 100 <= top + 1e-9


def test_ltcg_stacking_zero_bracket(params):
    """With no ordinary income, modest LTCG sits entirely in the 0% tier."""
    zero_top = params["ltcg_brackets"]["mfj"][0]["upto"]
    std = params["standard_deduction"]["mfj"]
    r = compute_year_tax(_inp(realized_ltcg=zero_top + std - 1000), params)
    assert r.federal == pytest.approx(0.0, abs=0.5)


def test_ltcg_stacked_on_ordinary_costs_more_than_alone(params):
    """Ordinary income pushes LTCG out of the 0% tier — stacking, not parallel brackets."""
    alone = compute_year_tax(_inp(realized_ltcg=100_000), params).federal
    with_ordinary = compute_year_tax(
        _inp(wages=200_000, realized_ltcg=100_000), params
    ).federal
    wages_only = compute_year_tax(_inp(wages=200_000), params).federal
    assert with_ordinary - wages_only > alone


def test_ss_taxation_phases(params):
    """Below base1: 0% taxable. Far above base2: exactly 85% taxable."""
    ss = 40_000
    low = compute_year_tax(_inp(ss_benefits=ss), params)
    assert low.taxable_ss == 0.0
    high = compute_year_tax(_inp(ss_benefits=ss, other_ordinary=500_000), params)
    assert high.taxable_ss == pytest.approx(0.85 * ss)


def test_ss_taxable_share_monotonic_in_other_income(params):
    prev = -1.0
    for other in range(0, 200_001, 5_000):
        r = compute_year_tax(_inp(ss_benefits=40_000, other_ordinary=other), params)
        assert r.taxable_ss >= prev - 1e-9
        prev = r.taxable_ss


def test_capital_loss_offset_capped(params):
    base = compute_year_tax(_inp(wages=100_000), params)
    small_loss = compute_year_tax(_inp(wages=100_000, realized_ltcg=-2_000), params)
    big_loss = compute_year_tax(_inp(wages=100_000, realized_ltcg=-50_000), params)
    capped = compute_year_tax(_inp(wages=100_000, realized_ltcg=-3_000), params)
    assert small_loss.agi == pytest.approx(base.agi - 2_000)
    assert big_loss.agi == pytest.approx(capped.agi)  # offset capped at $3,000


def test_roth_conversion_taxed_as_ordinary(params):
    a = compute_year_tax(_inp(roth_conversions=50_000), params)
    b = compute_year_tax(_inp(traditional_distributions=50_000), params)
    assert a.federal == pytest.approx(b.federal)


def test_indexing_raises_brackets(params):
    from finplan.taxes.params import index_params

    inflated = index_params(params, 1.30, "us_federal")
    for orig, adj in zip(params["ordinary_brackets"]["mfj"][:-1],
                         inflated["ordinary_brackets"]["mfj"][:-1]):
        assert adj["upto"] > orig["upto"]
        assert adj["rate"] == orig["rate"]
    # statutorily unindexed items stay put
    assert inflated["niit"] == params["niit"]
    assert inflated["ss_taxation"] == params["ss_taxation"]
