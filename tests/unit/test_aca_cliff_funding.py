"""ACA credit inside the withdrawal gross-up loop: the fixed point must converge
deterministically on both sides of the 400% FPL cliff (see withdrawal.py docstring).

MFJ household of 2: FPL 21,150, cliff MAGI = 84,600 (2026 params, cpi 1.0).
"""

import pytest

from finplan.model.accounts import Account, AccountType
from finplan.model.household import FilingStatus, Household, Person
from finplan.model.state import SimState
from finplan.policies.withdrawal import WithdrawalPolicy
from finplan.taxes.engine import FederalStateTaxEngine
from finplan.taxes.types import TaxInput

ENGINE = FederalStateTaxEngine(base_year=2026, state="none")


def _state():
    hh = Household(
        people=[Person(name="j", birth_year=1977), Person(name="q", birth_year=1975)],
        filing_status=FilingStatus.MFJ,
    )
    accounts = [Account(id="ira", type=AccountType.TRADITIONAL, owner="j",
                        balance=5_000_000)]
    return SimState(household=hh, accounts=accounts)


def _inp():
    return TaxInput(
        year=2035, filing_status=FilingStatus.MFJ, ages={"j": 60, "q": 62},
        cpi_factor=1.0, aca_benchmark_premium=24_000, aca_household_size=2,
    )


def _fund(base_need):
    return WithdrawalPolicy(["traditional"]).fund(base_need, 0.0, _state(), ENGINE, _inp())


def _self_consistent(res):
    final = ENGINE.compute(WithdrawalPolicy._input_with_withdrawals(_inp(), res))
    return final.aca_credit == pytest.approx(res.tax.aca_credit, abs=0.01)


def test_under_cliff_keeps_credit():
    res = _fund(60_000)
    assert res.unfunded == pytest.approx(0, abs=1.5)
    assert res.tax.aca_credit > 0
    assert res.tax.aca_fpl_pct <= 4.0
    assert _self_consistent(res)


def test_forced_over_cliff_converges_without_credit():
    res = _fund(150_000)
    assert res.unfunded == pytest.approx(0, abs=1.5)
    assert res.tax.aca_credit == 0.0
    assert res.tax.aca_fpl_pct > 4.0
    assert _self_consistent(res)


def test_knife_edge_is_deterministic_and_conservative():
    # cliff MAGI 84,600: with-credit after-tax cash there is ~94,382, so needs just
    # under/over that land on opposite sides of the cliff
    under = _fund(94_200)
    assert under.tax.aca_credit > 0
    assert under.tax.aca_fpl_pct <= 4.0
    assert _self_consistent(under)

    over = _fund(94_500)
    assert over.unfunded == pytest.approx(0, abs=1.5)
    assert over.tax.aca_credit == 0.0
    assert _self_consistent(over)

    # deterministic: identical reruns produce identical resolutions
    again = _fund(94_500)
    assert again.total_withdrawn == pytest.approx(over.total_withdrawn, abs=0.01)
    assert again.tax.aca_credit == over.tax.aca_credit
