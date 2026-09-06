"""Pydantic models for the *resolved* scenario config.

Overlays are partial dicts and are never validated alone; validation happens after
composition (config.compose) and snapshot resolution (config.loader).
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

YearRefT = int | str


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class MetaCfg(StrictModel):
    name: str = "unnamed"
    description: str = ""


class SimCfg(StrictModel):
    start_year: int
    horizon: YearRefT = "death"          # "death" or explicit end year


class PersonCfg(StrictModel):
    name: str
    birth_year: int
    retirement_age: int | None = None
    ss_claim_age: int | None = None
    ss_pia_monthly: float | None = None
    # Nominal covered earnings by calendar year, from the ssa.gov earnings record.
    # When present, the engine RECOMPUTES the PIA at build time: these years (before
    # sim.start_year) plus projected FICA-taxable income streams through retirement,
    # so retire-early scenarios automatically get the lower benefit. Overrides
    # ss_pia_monthly. Entries at/after sim.start_year are ignored (streams win).
    ss_earnings_history: dict[int, float] | None = None
    life_expectancy_age: int = 95


class HouseholdCfg(StrictModel):
    filing_status: Literal["single", "mfj"]
    people: list[PersonCfg] = Field(min_length=1, max_length=2)


_YIELD_KEYS = {"interest", "us_gov_interest", "muni_interest",
               "qualified_dividends", "ordinary_dividends", "ltcg_distributions"}


class AccountCfg(StrictModel):
    id: str
    type: Literal["taxable", "traditional", "roth", "hsa", "cash", "529"]
    owner: str | None = None
    balance: float = 0.0
    cost_basis: float | None = None      # defaults: taxable/roth/529 -> balance; else 0
    allocation: dict[str, float] | None = None
    beneficiary: str | None = None
    # taxable accounts only: annual yield by tax character, as fraction of balance
    # (e.g. {qualified_dividends: 0.015}). Reinvested + taxed annually. Cash accounts
    # are taxed automatically on their full return - no yields entry needed.
    yields: dict[str, float] | None = None
    # Employer plans (401k/403b) held at the sponsoring employer at separation:
    # withdrawals are penalty-exempt if the owner separates in or after the year
    # they turn 55 (the engine checks the age condition; the flag marks eligibility).
    # Never true for IRAs or plans that would be rolled over before withdrawing.
    rule_of_55: bool = False

    @model_validator(mode="after")
    def _check_yields(self):
        if self.yields:
            bad = set(self.yields) - _YIELD_KEYS
            if bad:
                raise ValueError(f"account {self.id!r}: unknown yield keys {sorted(bad)}; "
                                 f"allowed: {sorted(_YIELD_KEYS)}")
        if self.rule_of_55:
            if self.type not in ("traditional", "roth"):
                raise ValueError(f"account {self.id!r}: rule_of_55 only applies to "
                                 f"traditional/roth employer plans")
            if self.owner is None:
                raise ValueError(f"account {self.id!r}: rule_of_55 requires an owner "
                                 f"(the separation-age check needs their birth year)")
        return self


class IncomeCfg(StrictModel):
    id: str
    owner: str | None = None
    kind: Literal["salary", "business", "pension", "rental", "other"] = "salary"
    annual: float
    start: YearRefT
    end: YearRefT
    growth_real: float = 0.0
    taxable: bool = True
    fica: bool = True
    phantom: bool = False   # taxable but produces NO cash (undistributed K-1 share)


class ExpenseCfg(StrictModel):
    id: str
    annual: float
    start: YearRefT
    end: YearRefT
    growth_real: float = 0.0
    discretionary: bool = False
    education: bool = False
    beneficiary: str | None = None   # education streams: draw this kid's 529 first
    # This stream is the ACA marketplace premium: its amount doubles as the benchmark
    # (SLCSP proxy) for the premium tax credit and its start/end are the coverage
    # years. The stream still charges the FULL premium; the credit lands in taxes.
    aca: bool = False


class EventCfg(StrictModel):
    id: str
    year: YearRefT
    cash: float = 0.0
    taxable_as: Literal["none", "ordinary", "ltcg"] = "none"
    education: bool = False
    beneficiary: str | None = None   # education events: draw this kid's 529 first


class SpendingPolicyCfg(StrictModel):
    # fixed_real: spend every expense stream as configured.
    # guardrail: in retirement (no wage income), after a year with a negative REAL
    # stock return, cut `discretionary: true` expense streams by cut_fraction.
    type: Literal["fixed_real", "guardrail"] = "fixed_real"
    cut_fraction: float = 0.5

    @model_validator(mode="after")
    def _check(self):
        if not (0.0 <= self.cut_fraction <= 1.0):
            raise ValueError("cut_fraction must be between 0 and 1")
        return self


class WithdrawalPolicyCfg(StrictModel):
    # entries are account types (taxable, traditional, ...) or specific account ids
    order: list[str] = ["cash", "taxable", "traditional", "roth", "hsa"]


class PlannedContributionCfg(StrictModel):
    account: str
    amount: float | Literal["max"] = "max"   # "max" = the indexed statutory limit
    owner: str | None = None                 # defaults to the account's owner
    # Optional active window (inclusive YearRefs; "retirement" resolves per owner).
    # Lets a policy change mid-career: {amount: 18000, end: 2026} then
    # {amount: max, start: 2027} on the same account.
    start: YearRefT | None = None
    end: YearRefT | None = None


class ContributionPolicyCfg(StrictModel):
    # While working: pre-tax elective deferrals (traditional 401k, HSA) reduce taxable
    # wages; employer match is a % of the owner's salary deposited pre-tax on top.
    pretax: list[PlannedContributionCfg] = []
    posttax: list[PlannedContributionCfg] = []   # Roth 401k etc.: after-tax payroll money
    match_pct: dict[str, float] = {}         # account id -> fraction of owner's salary
    plan_529: list[PlannedContributionCfg] = []  # after-tax; MI-deductible up to cap
    # Whatever cash is left after spending/taxes goes to the first of these sinks:
    priority: list[str] = ["taxable"]


class RothConversionPolicyCfg(StrictModel):
    # fill_to_magi = fill_bracket PLUS a MAGI ceiling: convert up to the bracket top
    # but never past the cap. magi_cap "aca_cliff" resolves to margin x 400% x FPL
    # (household size from the ACA config) in years ACA coverage is active — the
    # subsidy-aware conversion ladder. A float cap is start-year real dollars.
    type: Literal["none", "fixed", "fill_bracket", "fill_to_magi"] = "none"
    amount: float | None = None          # fixed
    bracket_top: float | None = None     # fill_bracket / fill_to_magi, e.g. 0.12
    magi_cap: float | Literal["aca_cliff"] | None = None   # fill_to_magi
    margin: float = 0.98                 # safety factor: conversions run BEFORE the
                                         # funding withdrawals that also raise MAGI
    start: YearRefT | None = None
    end: YearRefT | None = None

    @model_validator(mode="after")
    def _check(self):
        if self.type == "fixed" and self.amount is None:
            raise ValueError("roth_conversion type 'fixed' requires 'amount'")
        if self.type in ("fill_bracket", "fill_to_magi") and self.bracket_top is None:
            raise ValueError(f"roth_conversion type {self.type!r} requires 'bracket_top'")
        if self.type == "fill_to_magi" and self.magi_cap is None:
            raise ValueError("roth_conversion type 'fill_to_magi' requires 'magi_cap'")
        if not (0.0 < self.margin <= 1.0):
            raise ValueError("margin must be in (0, 1]")
        return self


class SeppPlanCfg(StrictModel):
    # 72(t) substantially-equal-periodic-payment plan: a forced, penalty-free,
    # fixed-NOMINAL annual distribution from one traditional account. `annual` is in
    # start-year real dollars; it converts to nominal at the plan's first payment and
    # stays flat (SEPP payments don't index). Payments run from `start` through the
    # later of 5 payments or the year the owner reaches 59.5 — the IRS minimum; the
    # engine models stopping as soon as allowed. The payment AMOUNT must be computed
    # outside the model (IRS methods, 120% mid-term AFR cap) — CPA territory.
    account: str
    annual: float
    start: YearRefT


class RebalancePolicyCfg(StrictModel):
    type: Literal["none", "annual_to_target"] = "none"


class PoliciesCfg(StrictModel):
    spending: SpendingPolicyCfg = SpendingPolicyCfg()
    withdrawal: WithdrawalPolicyCfg = WithdrawalPolicyCfg()
    contribution: ContributionPolicyCfg = ContributionPolicyCfg()
    roth_conversion: RothConversionPolicyCfg = RothConversionPolicyCfg()
    sepp: list[SeppPlanCfg] = []
    rebalance: RebalancePolicyCfg = RebalancePolicyCfg()


class DeterministicMarketCfg(StrictModel):
    real_returns: dict[str, float] = {"stocks": 0.05, "bonds": 0.015, "cash": 0.0}
    inflation: float = 0.025


class MCAssetCfg(StrictModel):
    real_mean: float
    vol: float


class MonteCarloMarketCfg(StrictModel):
    n_paths: int = 2000
    assets: dict[str, MCAssetCfg] = {
        "stocks": MCAssetCfg(real_mean=0.05, vol=0.17),
        "bonds": MCAssetCfg(real_mean=0.015, vol=0.06),
        "cash": MCAssetCfg(real_mean=0.0, vol=0.01),
    }
    inflation_mean: float = 0.025
    inflation_vol: float = 0.015
    # pairwise correlations, keys like "stocks_bonds", "stocks_inflation". Defaults are
    # the calibrated planning values (mild stock/bond diversification, inflation hurts
    # both, bonds more); pass {} explicitly for independent series.
    correlation: dict[str, float] = {
        "stocks_bonds": -0.10, "stocks_inflation": -0.20, "bonds_inflation": -0.40,
    }


class HistoricalMarketCfg(StrictModel):
    source: Literal["shiller"] = "shiller"
    window: Literal["rolling"] = "rolling"


class MarketCfg(StrictModel):
    deterministic: DeterministicMarketCfg = DeterministicMarketCfg()
    monte_carlo: MonteCarloMarketCfg = MonteCarloMarketCfg()
    historical: HistoricalMarketCfg = HistoricalMarketCfg()


class AcaSizeStepCfg(StrictModel):
    through: YearRefT       # inclusive; int year or a YearRef like "age:alex:65"
    size: int


class AcaCfg(StrictModel):
    # Premium tax credit modeling. Active only when BOTH enabled=true and some
    # expense stream carries `aca: true` (so base configs stay inert by default).
    enabled: bool = True
    household_size: int | None = None    # None -> len(household.people)
    # Tax-family size steps (kids age off the return); first step whose `through`
    # covers the year wins; overrides household_size when non-empty.
    household_size_schedule: list[AcaSizeStepCfg] = []


class TaxCfg(StrictModel):
    regime: Literal["flat_stub", "us_federal"] = "us_federal"
    state: Literal["none", "michigan"] = "none"
    base_params_year: int = 2026
    flat_effective_rate: float = 0.22    # used only by regime=flat_stub
    # QBI (s199A): 20% of business income, limited by 50% of allocable W-2 wages.
    # Set the wage cap (start-year dollars, CPI-indexed) from the actual return:
    # line 13 when the wage limit binds. None disables QBI.
    qbi_wage_cap: float | None = None
    aca: AcaCfg = AcaCfg()


class ScenarioConfig(StrictModel):
    meta: MetaCfg = MetaCfg()
    sim: SimCfg
    household: HouseholdCfg
    accounts_from: str | None = None     # e.g. "snapshots/latest"; resolved by loader
    accounts: list[AccountCfg] = []
    income: list[IncomeCfg] = []
    expenses: list[ExpenseCfg] = []
    events: list[EventCfg] = []
    policies: PoliciesCfg = PoliciesCfg()
    market: MarketCfg = MarketCfg()
    taxes: TaxCfg = TaxCfg()

    @model_validator(mode="after")
    def _cross_checks(self):
        names = {p.name for p in self.household.people}
        for a in self.accounts:
            if a.owner is not None and a.owner not in names:
                raise ValueError(f"account {a.id!r}: unknown owner {a.owner!r}")
        for s in self.income:
            if s.owner is not None and s.owner not in names:
                raise ValueError(f"income {s.id!r}: unknown owner {s.owner!r}")
        ids = [a.id for a in self.accounts]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate account ids")
        accounts_by_id = {a.id: a for a in self.accounts}
        sepp_accounts = [s.account for s in self.policies.sepp]
        if len(sepp_accounts) != len(set(sepp_accounts)):
            raise ValueError("multiple sepp plans on the same account")
        for s in self.policies.sepp:
            acct = accounts_by_id.get(s.account)
            if acct is None:
                raise ValueError(f"sepp plan: unknown account {s.account!r}")
            if acct.type != "traditional":
                raise ValueError(f"sepp plan on {s.account!r}: account must be traditional")
            if acct.owner is None:
                raise ValueError(f"sepp plan on {s.account!r}: account needs an owner "
                                 f"(payment duration depends on their age)")
        aca_streams = [e.id for e in self.expenses if e.aca]
        if len(aca_streams) > 1:
            raise ValueError(f"at most one expense stream may set aca: true; got {aca_streams}")
        for p in self.household.people:
            if p.ss_earnings_history and self.sim.start_year - p.birth_year >= 62:
                raise ValueError(
                    f"person {p.name!r}: ss_earnings_history recompute only supports people "
                    f"under 62 at sim start (today's-dollars convention has no COLA chain); "
                    f"enter ss_pia_monthly directly instead"
                )
        return self
