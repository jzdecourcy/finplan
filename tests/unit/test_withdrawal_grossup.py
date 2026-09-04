"""Gross-up solver: funding an after-tax need from pre-tax accounts must withdraw the
correct grossed-up amount, converging to within $1."""

import pytest

from finplan.model.accounts import Account, AccountType
from finplan.model.household import FilingStatus, Household, Person
from finplan.model.state import SimState
from finplan.policies.withdrawal import WithdrawalPolicy
from finplan.taxes.types import FlatTaxStub, TaxInput


def _state(accounts):
    hh = Household(
        people=[Person(name="sam", birth_year=1960)], filing_status=FilingStatus.SINGLE
    )
    return SimState(household=hh, accounts=accounts)


def _inp():
    return TaxInput(year=2030, filing_status=FilingStatus.SINGLE, ages={"sam": 70})


def test_grossup_from_traditional_flat_rate():
    """Need $50k after tax at flat 20%: must withdraw 50k/(1-0.2) = 62,500."""
    state = _state([Account(id="ira", type=AccountType.TRADITIONAL, owner="sam",
                            balance=1_000_000)])
    policy = WithdrawalPolicy(["traditional"])
    res = policy.fund(50_000, 0.0, state, FlatTaxStub(0.20), _inp())
    assert res.total_withdrawn == pytest.approx(62_500, abs=1.5)
    assert res.tax.total == pytest.approx(12_500, abs=1.5)
    assert res.unfunded == pytest.approx(0, abs=1.5)


def test_tax_free_source_needs_no_grossup():
    state = _state([Account(id="cash", type=AccountType.CASH, balance=100_000)])
    res = WithdrawalPolicy(["cash"]).fund(50_000, 0.0, state, FlatTaxStub(0.20), _inp())
    assert res.total_withdrawn == pytest.approx(50_000, abs=1.0)
    assert res.tax.total == pytest.approx(0, abs=0.5)


def test_order_respected_cash_before_traditional():
    cash = Account(id="cash", type=AccountType.CASH, balance=30_000)
    ira = Account(id="ira", type=AccountType.TRADITIONAL, owner="sam", balance=500_000)
    state = _state([cash, ira])
    res = WithdrawalPolicy(["cash", "traditional"]).fund(
        50_000, 0.0, state, FlatTaxStub(0.20), _inp()
    )
    assert cash.balance == 0
    assert res.withdrawals["cash"].amount == pytest.approx(30_000)
    # remaining 20k after-tax from IRA -> 25k pre-tax
    assert res.withdrawals["ira"].amount == pytest.approx(25_000, abs=2.0)


def test_exhaustion_reports_unfunded():
    state = _state([Account(id="cash", type=AccountType.CASH, balance=10_000)])
    res = WithdrawalPolicy(["cash"]).fund(50_000, 0.0, state, FlatTaxStub(0.20), _inp())
    assert res.total_withdrawn == pytest.approx(10_000)
    assert res.unfunded == pytest.approx(40_000, abs=1.0)


def test_taxable_gains_grossup():
    """$100k balance with $40k basis: 60% of each withdrawal is LTCG taxed at 15%."""
    state = _state([Account(id="brk", type=AccountType.TAXABLE, owner="sam",
                            balance=100_000, cost_basis=40_000)])
    res = WithdrawalPolicy(["taxable"]).fund(50_000, 0.0, state, FlatTaxStub(0.20), _inp())
    # withdraw w: tax = 0.15 * 0.6w  ->  w = 50k / (1 - 0.09)
    assert res.total_withdrawn == pytest.approx(50_000 / 0.91, abs=2.0)
