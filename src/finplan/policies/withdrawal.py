"""Ordered, tax-aware withdrawal funding with gross-up iteration.

The core problem: withdrawing to cover spending changes the tax bill, which changes how
much must be withdrawn. `fund()` iterates withdraw -> recompute tax -> withdraw shortfall
until the gap is under $1 (converges in a handful of iterations because marginal rates
are < 100%).

ACA premium tax credit interaction: the credit shrinks as withdrawals raise MAGI and
vanishes above the 400% FPL cliff, so tax remains weakly INCREASING in withdrawals and
the loop stays monotone (withdrawals accumulate against mutable accounts, never
reversed). Consequences:
  * if spending is fundable with MAGI at or under the cliff, the loop approaches that
    fixed point from below and stops there — the credit is preserved;
  * if not, the first withdrawal crossing the cliff jumps `required` by the full lost
    credit and the loop keeps withdrawing, converging on the no-credit side;
  * knife-edge cases therefore resolve deterministically to the no-credit (conservative)
    side — no oscillation is possible because state never moves backward;
  * on _MAX_ITER exhaustion the final authoritative recompute below still records a tax
    result self-consistent with the withdrawals actually executed.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace

from finplan.model.accounts import Account, AccountType, WithdrawalResult
from finplan.model.household import Household
from finplan.model.state import SimState
from finplan.taxes.types import TaxEngine, TaxInput, TaxResult

_TOLERANCE = 1.0
_MAX_ITER = 25


def rule_of_55_applies(acct: Account, household: Household, year: int) -> bool:
    """Penalty exception for employer-plan withdrawals after separating at 55+.

    The account flag marks eligibility (held at the sponsoring employer); the law's
    condition — separation from service in or after the calendar year the owner turns
    55 — is checked here against the owner's modeled retirement year.
    """
    if not acct.rule_of_55 or acct.owner is None:
        return False
    p = household.person(acct.owner)
    ry = p.retirement_year
    return ry is not None and year >= ry and ry - p.birth_year >= 55


@dataclass
class FundingResult:
    tax: TaxResult
    withdrawals: dict[str, WithdrawalResult] = field(default_factory=dict)  # account id ->
    total_withdrawn: float = 0.0
    unfunded: float = 0.0


class WithdrawalPolicy:
    def __init__(self, order: list[str]):
        self.order = order

    def _accounts_in_order(self, state: SimState) -> list[Account]:
        ordered: list[Account] = []
        for entry in self.order:
            if entry in {t.value for t in AccountType}:
                ordered.extend(
                    a for a in state.accounts if a.type.value == entry and a not in ordered
                )
            else:
                acct = state.account(entry)
                if acct not in ordered:
                    ordered.append(acct)
        return ordered

    def fund(
        self,
        base_need: float,
        inflows: float,
        state: SimState,
        tax_engine: TaxEngine,
        tax_input: TaxInput,
    ) -> FundingResult:
        """Cover base_need (spending + event outflows) plus taxes out of inflows and,
        if needed, ordered account withdrawals. Mutates account balances."""
        ordered = self._accounts_in_order(state)
        ages = tax_input.ages
        result = FundingResult(tax=tax_engine.compute(tax_input))
        for _ in range(_MAX_ITER):
            inp = self._input_with_withdrawals(tax_input, result)
            result.tax = tax_engine.compute(inp)
            required = base_need + result.tax.total - inflows
            gap = required - result.total_withdrawn
            if gap <= _TOLERANCE:
                break
            took_any = False
            for acct in ordered:
                if gap <= _TOLERANCE:
                    break
                owner_age = ages.get(acct.owner) if acct.owner else max(ages.values())
                qualified = acct.type not in (AccountType.HSA, AccountType.PLAN_529)
                res = acct.withdraw(
                    gap,
                    owner_age=owner_age,
                    qualified=qualified,
                    penalty_exempt=rule_of_55_applies(
                        acct, state.household, tax_input.year
                    ),
                )
                if res.amount > 0:
                    took_any = True
                    prev = result.withdrawals.setdefault(acct.id, WithdrawalResult())
                    prev.amount += res.amount
                    prev.ordinary_income += res.ordinary_income
                    prev.realized_ltcg += res.realized_ltcg
                    prev.penalty_base += res.penalty_base
                    prev.tax_free += res.tax_free
                    result.total_withdrawn += res.amount
                    gap -= res.amount
            if not took_any:
                break  # accounts exhausted
        inp = self._input_with_withdrawals(tax_input, result)
        result.tax = tax_engine.compute(inp)
        result.unfunded = max(
            0.0, base_need + result.tax.total - inflows - result.total_withdrawn
        )
        return result

    @staticmethod
    def _input_with_withdrawals(base: TaxInput, result: FundingResult) -> TaxInput:
        ordinary = sum(w.ordinary_income for w in result.withdrawals.values())
        ltcg = sum(w.realized_ltcg for w in result.withdrawals.values())
        penalty = sum(w.penalty_base for w in result.withdrawals.values())
        return replace(
            base,
            traditional_distributions=base.traditional_distributions + ordinary,
            realized_ltcg=base.realized_ltcg + ltcg,
            penalty_base=base.penalty_base + penalty,
        )
