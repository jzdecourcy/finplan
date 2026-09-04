"""Contribution routing.

Working years, before the funding loop:
- pre-tax elective deferrals (traditional 401k / HSA): reduce taxable wages (not FICA
  wages — deferrals stay FICA-taxable; HSA payroll deferrals do avoid FICA but we take
  the conservative side and keep them FICA-taxable, noted in knowledge/assumptions.md),
  bounded by the owner's remaining salary and the indexed statutory limit
- employer match: % of owner's salary, deposited pre-tax, no wage reduction
- 529 contributions: after-tax cash out, MI-deductible up to the cap

After the funding loop, any remaining surplus goes to the first `priority` sink.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from finplan.config.schema import ContributionPolicyCfg
from finplan.model.accounts import AccountType
from finplan.model.state import SimState


@dataclass
class PlannedContributions:
    wage_reduction: float = 0.0          # pre-tax deferrals (income tax base shrinks)
    cash_out_posttax: float = 0.0        # after-tax payroll contributions (Roth 401k)
    cash_out_529: float = 0.0            # after-tax cash consumed by 529 contributions
    mi_529_deductible: float = 0.0
    by_account: dict[str, float] = field(default_factory=dict)
    total: float = 0.0

    def add(self, acct_id: str, amount: float) -> None:
        self.by_account[acct_id] = self.by_account.get(acct_id, 0.0) + amount
        self.total += amount


def _limit_for(acct_type: AccountType, limits: dict, age: int) -> float:
    if acct_type is AccountType.TRADITIONAL:
        cap = limits["elective_401k"]
        if age >= 50:
            cap += limits["catchup_401k_50"]
        return cap
    if acct_type is AccountType.HSA:
        cap = limits["hsa_family"]
        if age >= 55:
            cap += limits["hsa_catchup_55"]
        return cap
    return float("inf")


class ContributionPolicy:
    def __init__(self, cfg: ContributionPolicyCfg):
        self.cfg = cfg

    def planned(
        self,
        state: SimState,
        wages_by_person: dict[str, float],
        ages: dict[str, int],
        limits: dict | None,
        cpi_factor: float,
    ) -> PlannedContributions:
        """Execute payroll-linked contributions (deferrals, match, 529). Mutates accounts."""
        out = PlannedContributions()
        remaining_wages = dict(wages_by_person)

        for pc in self.cfg.pretax:
            acct = state.account(pc.account)
            owner = pc.owner or acct.owner
            wages = remaining_wages.get(owner, 0.0)
            if wages <= 0:
                continue
            if pc.amount == "max":
                if limits is None:
                    raise ValueError(
                        "contribution amount 'max' requires the us_federal tax regime"
                    )
                cap = _limit_for(acct.type, limits, ages.get(owner, 0))
            else:
                cap = pc.amount * cpi_factor
            amount = min(cap, wages)
            if amount <= 0:
                continue
            acct.deposit(amount, is_basis=acct.type is not AccountType.TRADITIONAL)
            remaining_wages[owner] = wages - amount
            out.wage_reduction += amount
            out.add(acct.id, amount)

        for pc in self.cfg.posttax:
            acct = state.account(pc.account)
            owner = pc.owner or acct.owner
            if pc.amount == "max":
                raise ValueError("posttax contributions need an explicit amount")
            wages = remaining_wages.get(owner, 0.0)
            if wages <= 0:
                continue  # after-tax payroll contributions stop with the paycheck
            amount = min(pc.amount * cpi_factor, wages)
            acct.deposit(amount)
            out.cash_out_posttax += amount
            out.add(acct.id, amount)

        for acct_id, pct in self.cfg.match_pct.items():
            acct = state.account(acct_id)
            owner = acct.owner
            salary = wages_by_person.get(owner, 0.0)
            if salary <= 0:
                continue
            amount = pct * salary
            acct.deposit(amount, is_basis=False)
            out.add(acct.id, amount)

        for pc in self.cfg.plan_529:
            acct = state.account(pc.account)
            if pc.amount == "max":
                raise ValueError("529 contributions need an explicit amount")
            owner = pc.owner or acct.owner
            if owner is not None and remaining_wages.get(owner, 0.0) <= 0:
                continue  # 529 contributions stop when the owner stops earning
            amount = pc.amount * cpi_factor
            acct.deposit(amount)
            out.cash_out_529 += amount
            out.mi_529_deductible += amount
            out.add(acct.id, amount)

        return out

    def route_surplus(self, surplus: float, state: SimState) -> dict[str, float]:
        """Deposit end-of-year surplus into the first available priority sink.
        Money is never dropped: falls back to any cash account, then the cash buffer."""
        if surplus <= 0:
            return {}
        for entry in self.cfg.priority:
            targets = (
                [a for a in state.accounts if a.type.value == entry]
                if entry in {t.value for t in AccountType}
                else [state.account(entry)]
            )
            if targets:
                targets[0].deposit(surplus)
                return {targets[0].id: surplus}
        cash_accounts = [a for a in state.accounts if a.type is AccountType.CASH]
        if cash_accounts:
            cash_accounts[0].deposit(surplus)
            return {cash_accounts[0].id: surplus}
        state.cash_buffer += surplus
        return {"cash_buffer": surplus}
