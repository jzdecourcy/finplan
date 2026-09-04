"""Construct a Simulation (domain objects + market model + tax engine) from a validated
ScenarioConfig."""

from __future__ import annotations

import copy

from finplan.config.schema import ScenarioConfig
from finplan.engine.simulator import Simulation
from finplan.markets.deterministic import DeterministicMarket
from finplan.model.accounts import Account, AccountType
from finplan.model.events import Event
from finplan.model.household import FilingStatus, Household, Person
from finplan.model.refs import RefContext
from finplan.model.streams import ExpenseStream, IncomeStream
from finplan.ss.pia import compute_pia_monthly
from finplan.taxes.types import FlatTaxStub, TaxEngine


def build_household(cfg: ScenarioConfig) -> Household:
    people = [
        Person(
            name=p.name,
            birth_year=p.birth_year,
            retirement_age=p.retirement_age,
            ss_claim_age=p.ss_claim_age,
            ss_pia_monthly=p.ss_pia_monthly,
            life_expectancy_age=p.life_expectancy_age,
        )
        for p in cfg.household.people
    ]
    return Household(people=people, filing_status=FilingStatus(cfg.household.filing_status))


def _income_streams(cfg: ScenarioConfig) -> list[IncomeStream]:
    return [
        IncomeStream(
            id=s.id, annual=s.annual, start=s.start, end=s.end,
            growth_real=s.growth_real, owner=s.owner, kind=s.kind,
            taxable=s.taxable, fica=s.fica, phantom=s.phantom,
        )
        for s in cfg.income
    ]


def derived_pias(cfg: ScenarioConfig) -> dict[str, float]:
    """Recomputed monthly PIAs (today's dollars) for people with an ss_earnings_history.

    Historical years before sim.start_year come from the SSA record; sim years through
    each stream's own end (e.g. `end: retirement`) are projected from the person's
    FICA-taxable income streams in start-year real dollars, capped at the current SS
    wage base — so scenarios that retire earlier automatically insert zero years.
    """
    with_history = [p for p in cfg.household.people if p.ss_earnings_history]
    if not with_history:
        return {}
    people = cfg.household.people
    ctx = RefContext(
        birth_years={p.name: p.birth_year for p in people},
        retirement_years={
            p.name: p.birth_year + p.retirement_age
            for p in people if p.retirement_age is not None
        },
        horizon_year=max(p.birth_year + p.life_expectancy_age for p in people),
    )
    wage_base = None
    if cfg.taxes.regime == "us_federal":
        from finplan.taxes.params import load_federal  # noqa: PLC0415

        wage_base = load_federal(cfg.taxes.base_params_year)["fica"]["ss_wage_base"]
    incomes = _income_streams(cfg)
    out = {}
    for p in with_history:
        earnings = {
            int(y): float(v) for y, v in p.ss_earnings_history.items()
            if int(y) < cfg.sim.start_year
        }
        for year in range(cfg.sim.start_year, ctx.horizon_year + 1):
            covered = sum(
                s.amount_in(year, s.ctx_for(ctx), cpi_factor=1.0)
                for s in incomes
                if s.owner == p.name and s.fica and not s.phantom
            )
            if covered > 0:
                earnings[year] = min(covered, wage_base) if wage_base else covered
        out[p.name] = compute_pia_monthly(earnings, p.birth_year)
    return out


def _account_template(cfg: ScenarioConfig) -> list[Account]:
    accounts = []
    for a in cfg.accounts:
        atype = AccountType(a.type)
        if a.cost_basis is not None:
            basis = a.cost_basis
        elif atype in (AccountType.TAXABLE, AccountType.ROTH, AccountType.PLAN_529):
            basis = a.balance  # conservative default: no embedded gains assumed
        else:
            basis = 0.0
        allocation = a.allocation
        if allocation is None:
            allocation = (
                {"cash": 1.0} if atype is AccountType.CASH else {"stocks": 0.6, "bonds": 0.4}
            )
        accounts.append(
            Account(
                id=a.id,
                type=atype,
                owner=a.owner,
                balance=a.balance,
                cost_basis=basis,
                allocation=allocation,
                beneficiary=a.beneficiary,
                yields=a.yields,
                rule_of_55=a.rule_of_55,
            )
        )
    return accounts


def build_tax_engine(cfg: ScenarioConfig) -> TaxEngine:
    if cfg.taxes.regime == "flat_stub":
        return FlatTaxStub(cfg.taxes.flat_effective_rate)
    # Phase 2 wires regime=us_federal (+ state) here.
    from finplan.taxes.engine import FederalStateTaxEngine  # noqa: PLC0415

    return FederalStateTaxEngine.from_config(cfg.taxes)


def build_market(cfg: ScenarioConfig, mode: str):
    if mode == "det":
        return DeterministicMarket(cfg.market.deterministic)
    if mode == "mc":
        from finplan.markets.montecarlo import MonteCarloMarket  # noqa: PLC0415

        return MonteCarloMarket(cfg.market.monte_carlo)
    if mode == "hist":
        from finplan.markets.historical import HistoricalMarket  # noqa: PLC0415

        return HistoricalMarket(cfg.market.historical)
    raise ValueError(f"unknown mode {mode!r}")


def build_simulation(cfg: ScenarioConfig) -> Simulation:
    template = _account_template(cfg)
    household = build_household(cfg)
    for name, pia in derived_pias(cfg).items():
        household.person(name).ss_pia_monthly = pia
    return Simulation(
        cfg=cfg,
        household=household,
        incomes=_income_streams(cfg),
        expenses=[
            ExpenseStream(
                id=s.id, annual=s.annual, start=s.start, end=s.end,
                growth_real=s.growth_real, discretionary=s.discretionary,
                education=s.education, aca=s.aca,
            )
            for s in cfg.expenses
        ],
        events=[
            Event(id=e.id, year=e.year, cash=e.cash, taxable_as=e.taxable_as,
                  education=e.education)
            for e in cfg.events
        ],
        tax_engine=build_tax_engine(cfg),
        make_accounts=lambda: copy.deepcopy(template),
    )
