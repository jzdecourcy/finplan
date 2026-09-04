from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class AccountType(StrEnum):
    TAXABLE = "taxable"
    TRADITIONAL = "traditional"
    ROTH = "roth"
    HSA = "hsa"
    CASH = "cash"
    PLAN_529 = "529"


@dataclass
class WithdrawalResult:
    """Tax character of a single withdrawal."""

    amount: float = 0.0                 # total cash produced
    ordinary_income: float = 0.0        # traditional distributions, non-qualified earnings
    realized_ltcg: float = 0.0          # taxable-account gain realized (average-cost)
    penalty_base: float = 0.0           # amount subject to early-withdrawal penalty
    tax_free: float = 0.0               # roth qualified, basis return, qualified 529/HSA


@dataclass
class Account:
    id: str
    type: AccountType
    owner: str | None = None
    balance: float = 0.0
    cost_basis: float = 0.0             # taxable: lot basis (average-cost); roth: contribution basis
    allocation: dict[str, float] = field(default_factory=lambda: {"stocks": 0.6, "bonds": 0.4})
    beneficiary: str | None = None      # 529 only
    yields: dict[str, float] | None = None  # taxable only: annual yield by tax character

    def deposit(self, amount: float, *, is_basis: bool = True) -> None:
        assert amount >= 0
        self.balance += amount
        if is_basis and self.type in (AccountType.TAXABLE, AccountType.ROTH, AccountType.PLAN_529):
            self.cost_basis += amount

    def withdraw(
        self, amount: float, *, owner_age: int | None = None, qualified: bool = True
    ) -> WithdrawalResult:
        """Withdraw up to `amount`; returns the tax character of what came out.

        `qualified` marks 529/HSA withdrawals matched to qualified expenses. Early-withdrawal
        penalties are only *flagged* here (penalty_base); the tax engine prices them.
        """
        take = min(amount, self.balance)
        if take <= 0:
            return WithdrawalResult()
        res = WithdrawalResult(amount=take)
        t = self.type
        if t in (AccountType.CASH,):
            res.tax_free = take
        elif t is AccountType.TAXABLE:
            # Average-cost: gain fraction of every dollar withdrawn matches the account's.
            basis_fraction = (self.cost_basis / self.balance) if self.balance > 0 else 1.0
            basis_out = take * min(basis_fraction, 1.0)
            res.realized_ltcg = take - basis_out
            res.tax_free = basis_out
            self.cost_basis -= basis_out
        elif t is AccountType.TRADITIONAL:
            res.ordinary_income = take
            if owner_age is not None and owner_age < 59.5:
                res.penalty_base = take
        elif t is AccountType.ROTH:
            # Contribution basis comes out first, tax/penalty-free; earnings after.
            basis_out = min(take, self.cost_basis)
            earnings_out = take - basis_out
            self.cost_basis -= basis_out
            res.tax_free = basis_out
            if earnings_out > 0:
                if owner_age is not None and owner_age >= 59.5:
                    res.tax_free += earnings_out
                else:
                    res.ordinary_income = earnings_out
                    res.penalty_base = earnings_out
        elif t in (AccountType.HSA, AccountType.PLAN_529):
            if qualified:
                res.tax_free = take
                self.cost_basis = max(0.0, self.cost_basis - take)
            else:
                basis_fraction = (self.cost_basis / self.balance) if self.balance > 0 else 1.0
                basis_out = take * min(basis_fraction, 1.0)
                earnings_out = take - basis_out
                self.cost_basis -= basis_out
                res.tax_free = basis_out
                res.ordinary_income = earnings_out
                res.penalty_base = earnings_out
        self.balance -= take
        return res

    def grow(self, asset_returns: dict[str, float]) -> float:
        """Apply one year of returns; returns the dollar growth."""
        r = sum(w * asset_returns.get(asset, 0.0) for asset, w in self.allocation.items())
        delta = self.balance * r
        self.balance += delta
        return delta
