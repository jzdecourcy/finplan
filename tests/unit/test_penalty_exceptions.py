"""Early-withdrawal penalty exceptions: rule of 55 (employer plans, separation at 55+)
and 72(t) SEPP (forced fixed-nominal distributions). Both waive the 10% penalty only —
the money stays taxable as it otherwise would be."""

import pytest

from finplan.config.schema import ScenarioConfig
from finplan.engine.runner import run
from finplan.model.accounts import Account, AccountType
from finplan.model.household import FilingStatus, Household, Person
from finplan.model.state import SimState
from finplan.policies.withdrawal import WithdrawalPolicy, rule_of_55_applies
from finplan.taxes.types import FlatTaxStub, TaxInput


# --- Account.withdraw penalty_exempt flag ---


def test_traditional_exempt_withdrawal_taxed_but_not_penalized():
    acct = Account(id="401k", type=AccountType.TRADITIONAL, owner="sam", balance=100_000)
    res = acct.withdraw(20_000, owner_age=56, penalty_exempt=True)
    assert res.ordinary_income == pytest.approx(20_000)
    assert res.penalty_base == 0.0


def test_traditional_early_withdrawal_penalized_by_default():
    acct = Account(id="401k", type=AccountType.TRADITIONAL, owner="sam", balance=100_000)
    res = acct.withdraw(20_000, owner_age=56)
    assert res.penalty_base == pytest.approx(20_000)


def test_roth_earnings_exempt_still_taxed_but_not_penalized():
    acct = Account(id="roth401k", type=AccountType.ROTH, owner="sam",
                   balance=100_000, cost_basis=60_000)
    res = acct.withdraw(100_000, owner_age=56, penalty_exempt=True)
    assert res.tax_free == pytest.approx(60_000)          # basis out first
    assert res.ordinary_income == pytest.approx(40_000)   # earnings still taxable
    assert res.penalty_base == 0.0


# --- rule of 55 eligibility ---


def _household(retirement_age):
    return Household(
        people=[Person(name="sam", birth_year=1980, retirement_age=retirement_age)],
        filing_status=FilingStatus.SINGLE,
    )


def _flagged_401k(balance=500_000):
    return Account(id="401k", type=AccountType.TRADITIONAL, owner="sam",
                   balance=balance, rule_of_55=True)


def test_rule_of_55_applies_after_separating_at_55_plus():
    hh = _household(retirement_age=57)   # separates 2037 at 57
    assert rule_of_55_applies(_flagged_401k(), hh, 2038)
    assert not rule_of_55_applies(_flagged_401k(), hh, 2036)   # still working


def test_rule_of_55_denied_when_separating_before_55():
    hh = _household(retirement_age=50)
    assert not rule_of_55_applies(_flagged_401k(), hh, 2035)


def test_rule_of_55_requires_flag():
    acct = Account(id="ira", type=AccountType.TRADITIONAL, owner="sam", balance=500_000)
    assert not rule_of_55_applies(acct, _household(retirement_age=57), 2038)


def test_funding_from_flagged_401k_after_57_separation_has_no_penalty():
    hh = _household(retirement_age=57)
    acct = _flagged_401k()
    state = SimState(household=hh, accounts=[acct])
    inp = TaxInput(year=2038, filing_status=FilingStatus.SINGLE, ages={"sam": 58})
    res = WithdrawalPolicy(["traditional"]).fund(50_000, 0.0, state, FlatTaxStub(0.20), inp)
    assert res.tax.penalties == pytest.approx(0.0)
    # pure gross-up at 20%: 50k / 0.8
    assert res.total_withdrawn == pytest.approx(62_500, abs=1.5)


def test_funding_from_unflagged_traditional_pays_penalty():
    hh = _household(retirement_age=57)
    acct = Account(id="ira", type=AccountType.TRADITIONAL, owner="sam", balance=500_000)
    state = SimState(household=hh, accounts=[acct])
    inp = TaxInput(year=2038, filing_status=FilingStatus.SINGLE, ages={"sam": 58})
    res = WithdrawalPolicy(["traditional"]).fund(50_000, 0.0, state, FlatTaxStub(0.20), inp)
    assert res.tax.penalties > 0
    # gross-up at 30% (20% tax + 10% penalty): 50k / 0.7
    assert res.total_withdrawn == pytest.approx(50_000 / 0.7, abs=2.0)


# --- 72(t) SEPP simulation behavior ---


def _sepp_config(start_year_age_gap=0, sepp_start=2035, horizon=2042):
    """Sam, born 1980, retired before sim start; IRA under a 30k SEPP."""
    return {
        "sim": {"start_year": 2033, "horizon": horizon},
        "household": {
            "filing_status": "single",
            "people": [{"name": "sam", "birth_year": 1980, "retirement_age": 52,
                        "life_expectancy_age": 90}],
        },
        "accounts": [
            {"id": "ira", "type": "traditional", "owner": "sam", "balance": 1_000_000},
            {"id": "cash", "type": "cash", "balance": 500_000},
        ],
        "expenses": [{"id": "living", "annual": 40_000, "start": 2033, "end": 2042}],
        "policies": {
            "withdrawal": {"order": ["cash"]},
            "sepp": [{"account": "ira", "annual": 30_000, "start": sepp_start}],
        },
        "market": {
            "deterministic": {
                "real_returns": {"stocks": 0.0, "bonds": 0.0, "cash": 0.0},
                "inflation": 0.025,
            }
        },
        "taxes": {"regime": "flat_stub", "flat_effective_rate": 0.20},
    }


@pytest.fixture(scope="module")
def sepp_ledger():
    cfg = ScenarioConfig.model_validate(_sepp_config())
    return run(cfg, mode="det").ledger.set_index("year")


def test_sepp_pays_fixed_nominal_from_start(sepp_ledger):
    # First payment 2035: 30k at that year's price level (2 years of 2.5% inflation),
    # then flat NOMINAL through 2039 (5 payments; sam turns 59.5 during 2039-2040).
    first = 30_000 * 1.025**2
    for year in range(2035, 2040):
        assert sepp_ledger.loc[year, "sepp"] == pytest.approx(first)
    assert sepp_ledger.loc[2034, "sepp"] == 0.0
    assert sepp_ledger.loc[2040, "sepp"] == 0.0


def test_sepp_is_penalty_free_ordinary_income(sepp_ledger):
    row = sepp_ledger.loc[2035]
    assert row["tax_penalties"] == pytest.approx(0.0)
    # flat 20% on ordinary income: the SEPP distribution plus cash-account interest
    # (nominal cash return is taxable); spending itself is covered from cash, tax-free
    assert row["tax_total"] == pytest.approx(
        0.20 * (30_000 * 1.025**2 + row["interest_dividends"]), abs=1.0
    )


def test_sepp_five_payment_minimum_extends_past_59_half():
    # Start at age 57 (2037): 5 payments run through 2041 even though sam clears
    # 59.5 during 2040.
    cfg = ScenarioConfig.model_validate(_sepp_config(sepp_start=2037))
    ledger = run(cfg, mode="det").ledger.set_index("year")
    for year in range(2037, 2042):
        assert ledger.loc[year, "sepp"] > 0
    assert ledger.loc[2042, "sepp"] == 0.0


def test_sepp_validation_rejects_non_traditional_account():
    cfg = _sepp_config()
    cfg["policies"]["sepp"][0]["account"] = "cash"
    with pytest.raises(ValueError, match="must be traditional"):
        ScenarioConfig.model_validate(cfg)


def test_sepp_validation_rejects_unknown_account():
    cfg = _sepp_config()
    cfg["policies"]["sepp"][0]["account"] = "nope"
    with pytest.raises(ValueError, match="unknown account"):
        ScenarioConfig.model_validate(cfg)


def test_rule_of_55_validation_rejects_taxable_account():
    cfg = _sepp_config()
    cfg["accounts"].append({"id": "brk", "type": "taxable", "rule_of_55": True})
    with pytest.raises(ValueError, match="rule_of_55"):
        ScenarioConfig.model_validate(cfg)
