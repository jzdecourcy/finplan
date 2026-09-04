"""fill_to_magi Roth conversions: bracket fill capped by an ACA-aware MAGI ceiling.

MFJ household 2 (2026 params, cpi 1.0): FPL 21,150, cliff MAGI 84,600, so the
default 0.98 margin caps conversions at 82,908. Plain 12%-bracket fill with no
other income is 133,000 (bracket top 100,800 + standard deduction 32,200).
"""

import pytest

from finplan.config.schema import RothConversionPolicyCfg
from finplan.model.accounts import Account, AccountType
from finplan.model.household import FilingStatus, Household, Person
from finplan.model.refs import RefContext
from finplan.model.state import SimState
from finplan.policies.roth_conversion import RothConversionPolicy
from finplan.taxes.engine import FederalStateTaxEngine
from finplan.taxes.types import TaxInput

ENGINE = FederalStateTaxEngine(base_year=2026)
CTX = RefContext(birth_years={"sam": 1985}, retirement_years={"sam": 2040},
                 horizon_year=2080)
CAP = 0.98 * 4.00 * 21_150   # 82,908


def _state():
    hh = Household(people=[Person(name="sam", birth_year=1985)],
                   filing_status=FilingStatus.MFJ)
    return SimState(household=hh, accounts=[
        Account(id="ira", type=AccountType.TRADITIONAL, owner="sam", balance=1_000_000),
        Account(id="roth", type=AccountType.ROTH, owner="sam", balance=0, cost_basis=0),
    ])


def _policy(**kw):
    kw.setdefault("type", "fill_to_magi")
    kw.setdefault("bracket_top", 0.12)
    kw.setdefault("magi_cap", "aca_cliff")
    return RothConversionPolicy(RothConversionPolicyCfg(**kw))


def _inp(**kw):
    kw.setdefault("year", 2045)
    kw.setdefault("filing_status", FilingStatus.MFJ)
    kw.setdefault("ages", {"sam": 60})
    kw.setdefault("aca_benchmark_premium", 24_000)
    kw.setdefault("aca_household_size", 2)
    return TaxInput(**kw)


def test_cliff_cap_binds_below_bracket_fill():
    amt = _policy().conversion_amount(2045, CTX, _state(), ENGINE, _inp())
    assert amt == pytest.approx(CAP, abs=1.0)
    # and the resulting year stays under the cliff with the credit intact
    r = ENGINE.compute(_inp(roth_conversions=amt))
    assert r.aca_fpl_pct <= 4.0
    assert r.aca_credit > 0


def test_no_coverage_year_falls_back_to_bracket_fill():
    inp = _inp(aca_benchmark_premium=0.0, aca_household_size=0)
    amt = _policy().conversion_amount(2045, CTX, _state(), ENGINE, inp)
    assert amt == pytest.approx(133_000, abs=1.0)


def test_existing_income_reduces_headroom():
    amt = _policy().conversion_amount(
        2045, CTX, _state(), ENGINE, _inp(other_ordinary=30_000)
    )
    assert amt == pytest.approx(CAP - 30_000, abs=1.0)


def test_float_cap_in_real_dollars():
    amt = _policy(magi_cap=50_000).conversion_amount(2045, CTX, _state(), ENGINE, _inp())
    assert amt == pytest.approx(50_000, abs=1.0)


def test_requires_magi_cap():
    with pytest.raises(ValueError):
        RothConversionPolicyCfg(type="fill_to_magi", bracket_top=0.12)
