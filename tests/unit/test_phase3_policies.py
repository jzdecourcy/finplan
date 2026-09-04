"""Phase 3 policy tests: fill-to-bracket Roth conversions, RMD forcing, contribution
limits — against the real 2026 federal engine."""

import pytest

from finplan.config.schema import (
    ContributionPolicyCfg,
    PlannedContributionCfg,
    RothConversionPolicyCfg,
)
from finplan.model.accounts import Account, AccountType
from finplan.model.household import FilingStatus, Household, Person
from finplan.model.refs import RefContext
from finplan.model.state import SimState
from finplan.policies.contribution import ContributionPolicy
from finplan.policies.roth_conversion import RothConversionPolicy
from finplan.taxes.engine import FederalStateTaxEngine
from finplan.taxes.rmd import rmd_amount, rmd_start_age
from finplan.taxes.params import load_rmd_table
from finplan.taxes.types import TaxInput

ENGINE = FederalStateTaxEngine(base_year=2026)
CTX = RefContext(birth_years={"sam": 1985}, retirement_years={"sam": 2040},
                 horizon_year=2080)


def _retiree_state():
    hh = Household(people=[Person(name="sam", birth_year=1985)],
                   filing_status=FilingStatus.MFJ)
    return SimState(household=hh, accounts=[
        Account(id="ira", type=AccountType.TRADITIONAL, owner="sam", balance=1_000_000),
        Account(id="roth", type=AccountType.ROTH, owner="sam", balance=50_000,
                cost_basis=50_000),
    ])


def _inp(**kw):
    kw.setdefault("year", 2045)
    kw.setdefault("filing_status", FilingStatus.MFJ)
    kw.setdefault("ages", {"sam": 60})
    return TaxInput(**kw)


def test_fill_bracket_lands_at_bracket_top():
    """No other income: converting to the top of the 12% bracket means conversion =
    bracket top + standard deduction = 100,800 + 32,200 = 133,000."""
    policy = RothConversionPolicy(
        RothConversionPolicyCfg(type="fill_bracket", bracket_top=0.12)
    )
    state = _retiree_state()
    amt = policy.conversion_amount(2045, CTX, state, ENGINE, _inp())
    assert amt == pytest.approx(133_000, abs=1.0)


def test_fill_bracket_accounts_for_existing_income():
    policy = RothConversionPolicy(
        RothConversionPolicyCfg(type="fill_bracket", bracket_top=0.12)
    )
    state = _retiree_state()
    amt = policy.conversion_amount(
        2045, CTX, state, ENGINE, _inp(other_ordinary=50_000)
    )
    assert amt == pytest.approx(133_000 - 50_000, abs=1.0)


def test_fill_bracket_with_ss_interaction_stays_at_top():
    """With SS in the picture, converting drags more SS into taxability; the refinement
    loop must still land taxable ordinary income at the bracket top (within $1)."""
    from dataclasses import replace

    policy = RothConversionPolicy(
        RothConversionPolicyCfg(type="fill_bracket", bracket_top=0.12)
    )
    state = _retiree_state()
    inp = _inp(ages={"sam": 68}, ss_benefits=40_000)
    amt = policy.conversion_amount(2045, CTX, state, ENGINE, inp)
    result = ENGINE.compute(replace(inp, roth_conversions=amt))
    assert result.taxable_income == pytest.approx(100_800, abs=1.5)


def test_conversion_execute_moves_traditional_to_roth():
    state = _retiree_state()
    moved = RothConversionPolicy.execute(133_000, state)
    assert moved == pytest.approx(133_000)
    assert state.account("ira").balance == pytest.approx(867_000)
    assert state.account("roth").balance == pytest.approx(183_000)
    assert state.account("roth").cost_basis == pytest.approx(183_000)


def test_rmd_start_ages():
    assert rmd_start_age(1950) == 72
    assert rmd_start_age(1955) == 73
    assert rmd_start_age(1959) == 73
    assert rmd_start_age(1960) == 75
    assert rmd_start_age(1985) == 75


def test_rmd_amount_pub590b():
    """$400,000 prior-EOY balance at age 75: 400,000 / 24.6 = 16,260.16"""
    table = load_rmd_table()
    assert rmd_amount(400_000, 75, table) == pytest.approx(16_260.16, abs=0.01)
    assert rmd_amount(400_000, 90, table) == pytest.approx(400_000 / 12.2, abs=0.01)
    assert rmd_amount(400_000, 130, table) == pytest.approx(400_000 / 2.0, abs=0.01)


def test_pretax_401k_max_uses_indexed_limit():
    hh = Household(people=[Person(name="sam", birth_year=1985)],
                   filing_status=FilingStatus.MFJ)
    state = SimState(household=hh, accounts=[
        Account(id="401k", type=AccountType.TRADITIONAL, owner="sam", balance=0),
    ])
    policy = ContributionPolicy(ContributionPolicyCfg(
        pretax=[PlannedContributionCfg(account="401k")],
        match_pct={"401k": 0.04},
    ))
    fed_params, _ = ENGINE.params_for_year(1.0)
    planned = policy.planned(state, {"sam": 180_000}, {"sam": 41},
                             fed_params["limits"], 1.0)
    # deferral capped at 2026 elective limit; match on top
    assert planned.wage_reduction == pytest.approx(24_500)
    assert state.account("401k").balance == pytest.approx(24_500 + 0.04 * 180_000)


def test_catchup_50_applies():
    hh = Household(people=[Person(name="sam", birth_year=1970)],
                   filing_status=FilingStatus.MFJ)
    state = SimState(household=hh, accounts=[
        Account(id="401k", type=AccountType.TRADITIONAL, owner="sam", balance=0),
    ])
    policy = ContributionPolicy(ContributionPolicyCfg(
        pretax=[PlannedContributionCfg(account="401k")]
    ))
    fed_params, _ = ENGINE.params_for_year(1.0)
    planned = policy.planned(state, {"sam": 180_000}, {"sam": 56},
                             fed_params["limits"], 1.0)
    assert planned.wage_reduction == pytest.approx(24_500 + 8_000)
