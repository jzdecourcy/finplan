"""The annual simulation loop.

ORDERING CONTRACT (correctness-critical; do not reorder without updating golden tests):
  1. inflation/index      cumulative CPI factor; tax params index off it
  2. events               one-time cash in/out at this year's price level
  3. income + payroll     streams, Social Security; pre-tax deferrals/match/529 out of wages
  4. RMDs                 forced traditional distributions from PRIOR Dec-31 balances
  5. Roth conversions     policy sees income-so-far, so bracket-fill is honest
  6. spending             expense streams; education needs draw 529s first (qualified)
  7. fund the gap         tax-aware gross-up loop (withdraw -> retax -> repeat);
                          the ACA premium tax credit resolves INSIDE this loop (the
                          credit depends on MAGI, MAGI on withdrawals — see the
                          convergence notes in policies/withdrawal.py)
  8. final tax            single authoritative TaxResult recorded in the ledger
  9. surplus routing      leftover cash to the priority sink
 10. rebalance            per-account fixed allocations = implicit annual rebalance;
                          glidepaths are a Phase 6 feature
 11. grow                 apply this year's returns; record EOY traditional balances
 12. record               YearLedger row; failure = unfunded forced spending
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from finplan.config.schema import ScenarioConfig
from finplan.model.accounts import AccountType
from finplan.model.events import Event
from finplan.model.household import Household, Person
from finplan.model.refs import RefContext, resolve
from finplan.model.state import SimState, YearLedger
from finplan.model.streams import ExpenseStream, IncomeStream
from finplan.markets.base import ReturnPaths
from finplan.policies.contribution import ContributionPolicy
from finplan.policies.roth_conversion import RothConversionPolicy
from finplan.policies.withdrawal import WithdrawalPolicy
from finplan.taxes.params import load_rmd_table
from finplan.taxes.rmd import rmd_amount, rmd_start_age
from finplan.taxes.types import TaxEngine, TaxInput

# SSA claim-age adjustment relative to FRA 67 (stable statutory formula, not a tax param):
# reduction 5/9% per month for first 36 months early, 5/12% per month beyond;
# delayed retirement credit 8% per year past FRA, capped at 70.
_FRA = 67


def ss_claim_factor(claim_age: int) -> float:
    months = (claim_age - _FRA) * 12
    if months >= 0:
        return 1.0 + 0.08 * min(claim_age - _FRA, 70 - _FRA)
    early = -months
    first = min(early, 36)
    rest = max(0, early - 36)
    return 1.0 - first * (5 / 900) - rest * (5 / 1200)


def annual_ss_benefit(p: Person, year: int, cpi_factor: float) -> float:
    if p.ss_claim_age is None or p.ss_pia_monthly is None:
        return 0.0
    if p.age_in(year) < p.ss_claim_age:
        return 0.0
    return p.ss_pia_monthly * 12 * ss_claim_factor(p.ss_claim_age) * cpi_factor


@dataclass
class Simulation:
    cfg: ScenarioConfig
    household: Household
    incomes: list[IncomeStream]
    expenses: list[ExpenseStream]
    events: list[Event]
    tax_engine: TaxEngine
    make_accounts: "callable"      # () -> fresh list[Account] per path

    def ref_context(self) -> RefContext:
        hh = self.household
        horizon = (
            hh.horizon_year if self.cfg.sim.horizon == "death" else int(self.cfg.sim.horizon)
        )
        return RefContext(
            birth_years={p.name: p.birth_year for p in hh.people},
            retirement_years={
                p.name: p.retirement_year for p in hh.people if p.retirement_year is not None
            },
            horizon_year=horizon,
        )

    def years(self) -> list[int]:
        return list(range(self.cfg.sim.start_year, self.ref_context().horizon_year + 1))

    def _contribution_limits(self, cpi_factor: float) -> dict | None:
        if hasattr(self.tax_engine, "params_for_year"):
            fed_params, _ = self.tax_engine.params_for_year(cpi_factor)
            return fed_params["limits"]
        return None

    def simulate_path(self, paths: ReturnPaths, path_idx: int) -> list[YearLedger]:
        cfg = self.cfg
        hh = self.household
        ctx = self.ref_context()
        state = SimState(household=hh, accounts=self.make_accounts())
        withdrawal = WithdrawalPolicy(cfg.policies.withdrawal.order)
        contribution = ContributionPolicy(cfg.policies.contribution)
        conversion = RothConversionPolicy(cfg.policies.roth_conversion)
        rmd_table = load_rmd_table()
        aca_cfg = cfg.taxes.aca
        aca_enabled = aca_cfg.enabled and any(s.aca for s in self.expenses)
        prior_eoy_traditional = {
            a.id: a.balance for a in state.accounts if a.type is AccountType.TRADITIONAL
        }
        ledgers: list[YearLedger] = []
        cpi = 1.0
        years = self.years()
        for i, year in enumerate(years):
            if i > 0:
                cpi *= 1.0 + float(paths.inflation[path_idx, i - 1])
            led = YearLedger(year=year, cpi_factor=cpi)
            ages = {p.name: p.age_in(year) for p in hh.people}

            # 2. events
            education_out = 0.0
            for ev in self.events:
                if ev.occurs_in(year, ctx):
                    nominal = ev.cash * cpi
                    if nominal >= 0:
                        led.event_cash_in += nominal
                    elif ev.education:
                        education_out += -nominal
                    else:
                        led.event_cash_out += -nominal

            # 3. income + payroll contributions
            wages_by_person: dict[str, float] = {}
            business_income = 0.0      # all business income (for QBI) incl. phantom
            phantom_income = 0.0       # taxable but never hits cash
            for s in self.incomes:
                amt = s.amount_in(year, s.ctx_for(ctx), cpi)
                if amt <= 0:
                    continue
                if s.kind in ("salary", "business") and s.fica and not s.phantom:
                    key = s.owner or hh.people[0].name
                    wages_by_person[key] = wages_by_person.get(key, 0.0) + amt
                    led.wages += amt
                elif s.kind == "business":
                    business_income += amt
                    if s.phantom:
                        phantom_income += amt
                    else:
                        led.other_income += amt
                else:
                    led.other_income += amt
            for p in hh.people:
                led.ss_benefits += annual_ss_benefit(p, year, cpi)

            # 3b. investment yield, taxed annually. Taxable accounts: per-category yields
            # from config, treated as reinvested (basis grows; balance growth already
            # captures total return). Cash accounts: the full return IS taxable interest.
            year_returns = paths.year_returns(path_idx, i)
            inv = {"interest": 0.0, "us_gov_interest": 0.0, "muni_interest": 0.0,
                   "qualified_dividends": 0.0, "ordinary_dividends": 0.0,
                   "ltcg_distributions": 0.0}
            for acct in state.accounts:
                if acct.type is AccountType.TAXABLE and acct.yields:
                    for cat, rate in acct.yields.items():
                        dollars = acct.balance * rate
                        inv[cat] += dollars
                        acct.cost_basis += dollars   # reinvested distributions add basis
                        if cat != "ltcg_distributions":  # LTCG lands in realized_ltcg
                            led.interest_dividends += dollars
                elif acct.type is AccountType.CASH:
                    dollars = acct.balance * max(0.0, year_returns.get("cash", 0.0))
                    inv["interest"] += dollars
                    led.interest_dividends += dollars

            planned = contribution.planned(
                state, wages_by_person, ages, self._contribution_limits(cpi), cpi
            )

            # 4. RMDs (from prior Dec-31 balances; distribution lands as spendable cash)
            rmd_total = 0.0
            for acct in state.accounts:
                if acct.type is not AccountType.TRADITIONAL or acct.owner is None:
                    continue
                owner = hh.person(acct.owner)
                if ages[acct.owner] >= rmd_start_age(owner.birth_year):
                    amount = rmd_amount(
                        prior_eoy_traditional.get(acct.id, 0.0), ages[acct.owner], rmd_table
                    )
                    res = acct.withdraw(amount, owner_age=ages[acct.owner])
                    rmd_total += res.amount
            led.rmd = rmd_total

            # ACA premium tax credit inputs: the flagged stream's nominal amount is
            # the benchmark (SLCSP proxy); zero outside coverage years => inactive.
            aca_premium = 0.0
            aca_size = 0
            if aca_enabled:
                aca_premium = sum(
                    s.amount_in(year, ctx, cpi) for s in self.expenses if s.aca
                )
                aca_size = next(
                    (st.size for st in aca_cfg.household_size_schedule
                     if year <= resolve(st.through, ctx)),
                    aca_cfg.household_size or len(hh.people),
                )

            # 5. Roth conversions (policy sees wages, RMDs — income so far)
            base_inp = TaxInput(
                year=year,
                filing_status=hh.filing_status,
                ages=ages,
                cpi_factor=cpi,
                wages=led.wages - planned.wage_reduction,
                wages_by_person=wages_by_person,
                business=business_income,
                other_ordinary=led.other_income - (business_income - phantom_income),
                qbi_wage_cap=(
                    self.cfg.taxes.qbi_wage_cap * cpi
                    if self.cfg.taxes.qbi_wage_cap is not None else None
                ),
                interest=inv["interest"],
                us_gov_interest=inv["us_gov_interest"],
                tax_exempt_interest=inv["muni_interest"],
                ordinary_dividends=inv["ordinary_dividends"],
                qualified_dividends=inv["qualified_dividends"],
                # fund cap-gain distributions: recognized annually as LTCG (reinvested,
                # basis already stepped up above); withdrawal gains stack on top
                realized_ltcg=inv["ltcg_distributions"],
                traditional_distributions=rmd_total,
                ss_benefits=led.ss_benefits,
                mi_529_contributions=planned.mi_529_deductible,
                aca_benchmark_premium=aca_premium,
                aca_household_size=aca_size,
            )
            conv_amount = conversion.conversion_amount(
                year, ctx, state, self.tax_engine, base_inp
            )
            led.roth_conversion = RothConversionPolicy.execute(conv_amount, state)
            tax_input = replace(base_inp, roth_conversions=led.roth_conversion)

            # 6. spending; education needs draw 529s first (qualified, tax-free).
            # Guardrail policy: retired + prior year's real stock return negative ->
            # discretionary streams get cut by cut_fraction.
            cut = 0.0
            sp = cfg.policies.spending
            if sp.type == "guardrail" and i > 0 and led.wages == 0:
                prev = paths.year_returns(path_idx, i - 1)
                prev_infl = float(paths.inflation[path_idx, i - 1])
                real_stocks = (1 + prev.get("stocks", 0.0)) / (1 + prev_infl) - 1
                if real_stocks < 0:
                    cut = sp.cut_fraction
            general_spend = 0.0
            for s in self.expenses:
                amt = s.amount_in(year, ctx, cpi)
                if s.discretionary and cut > 0:
                    amt *= 1 - cut
                if s.education:
                    education_out += amt
                else:
                    general_spend += amt
            education_from_529 = 0.0
            if education_out > 0:
                for acct in state.accounts:
                    if acct.type is AccountType.PLAN_529 and education_out > 0:
                        res = acct.withdraw(education_out - education_from_529, qualified=True)
                        education_from_529 += res.amount
                        if education_from_529 >= education_out:
                            break
            led.spending = general_spend + education_out

            # 7-8. fund the gap; final tax
            inflows = (
                (led.wages - planned.wage_reduction)
                + led.other_income + led.ss_benefits + led.event_cash_in + rmd_total
            )
            base_need = (
                general_spend + (education_out - education_from_529)
                + led.event_cash_out + planned.cash_out_529 + planned.cash_out_posttax
            )
            funding = withdrawal.fund(base_need, inflows, state, self.tax_engine, tax_input)
            led.tax_total = funding.tax.total
            led.tax_federal = funding.tax.federal
            led.tax_state = funding.tax.state
            led.tax_fica = funding.tax.fica
            led.tax_penalties = funding.tax.penalties
            led.agi = funding.tax.agi
            led.taxable_income = funding.tax.taxable_income
            led.aca_gross_premium = aca_premium
            led.aca_magi = funding.tax.aca_magi
            led.aca_fpl_pct = funding.tax.aca_fpl_pct
            led.aca_credit = funding.tax.aca_credit
            if hasattr(self.tax_engine, "marginals"):
                final_inp = WithdrawalPolicy._input_with_withdrawals(tax_input, funding)
                led.marginal_rate_ordinary, _ = self.tax_engine.marginals(final_inp)
            else:
                led.marginal_rate_ordinary = funding.tax.marginal_rate_ordinary
            led.realized_ltcg = (
                inv["ltcg_distributions"]
                + sum(w.realized_ltcg for w in funding.withdrawals.values())
            )
            led.withdrawals_total = funding.total_withdrawn + education_from_529 + rmd_total
            led.shortfall_unfunded = funding.unfunded
            if funding.unfunded > 1.0:
                led.failed = True
                if not state.failed:
                    state.failed = True
                    state.first_failure_year = year

            # 9. surplus routing
            surplus = inflows + funding.total_withdrawn - base_need - funding.tax.total
            routed = contribution.route_surplus(surplus, state) if surplus > 0 else {}
            led.contributions_total = planned.total + sum(routed.values())

            # 10. rebalance: fixed per-account allocations are an implicit annual rebalance.

            # 11. grow
            for acct in state.accounts:
                if acct.type is AccountType.CASH:
                    acct.grow({k: year_returns.get("cash", 0.0) for k in acct.allocation})
                else:
                    acct.grow(year_returns)
            prior_eoy_traditional = {
                a.id: a.balance for a in state.accounts if a.type is AccountType.TRADITIONAL
            }

            # 12. record
            led.balances = {a.id: a.balance for a in state.accounts}
            led.net_worth = state.net_worth
            led.net_worth_real = state.net_worth / cpi
            ledgers.append(led)
        return ledgers
