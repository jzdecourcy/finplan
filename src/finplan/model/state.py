from __future__ import annotations

from dataclasses import dataclass, field, fields

from finplan.model.accounts import Account
from finplan.model.household import Household


@dataclass
class YearLedger:
    """One annual row of the simulation ledger. All dollar values nominal unless *_real."""

    year: int
    cpi_factor: float = 1.0

    # income
    wages: float = 0.0
    other_income: float = 0.0          # pension, rental, business, other streams
    ss_benefits: float = 0.0
    event_cash_in: float = 0.0
    interest_dividends: float = 0.0    # placeholder until taxable-yield modeling (Phase 3+)

    # forced / elective tax events
    rmd: float = 0.0
    sepp: float = 0.0                  # 72(t) SEPP distributions (penalty-free ordinary)
    roth_conversion: float = 0.0

    # outflows
    spending: float = 0.0
    event_cash_out: float = 0.0

    # taxes (Phase 1: total only; Phase 2 fills components)
    tax_total: float = 0.0
    tax_federal: float = 0.0
    tax_state: float = 0.0
    tax_fica: float = 0.0
    tax_penalties: float = 0.0
    agi: float = 0.0
    taxable_income: float = 0.0
    marginal_rate_ordinary: float = 0.0
    realized_ltcg: float = 0.0
    capital_loss_carryforward: float = 0.0   # unused capital loss carried INTO next year
    foreign_tax_credit: float = 0.0

    # ACA premium tax credit (all zero when no aca-flagged expense stream is active)
    aca_gross_premium: float = 0.0     # full benchmark premium charged as spending
    aca_magi: float = 0.0
    aca_fpl_pct: float = 0.0           # ratio: 2.25 = 225% of FPL
    aca_credit: float = 0.0

    # Medicare IRMAA (zero until someone reaches medicare_age)
    magi_irmaa: float = 0.0            # AGI + tax-exempt interest; sets IRMAA two years on
    tax_irmaa: float = 0.0             # Part B + D surcharge paid this year (in tax_total)
    irmaa_tier: int = 0

    # funding
    withdrawals_total: float = 0.0
    contributions_total: float = 0.0
    shortfall_unfunded: float = 0.0    # > 0 means the plan failed to fund spending this year

    # balances
    net_worth: float = 0.0
    net_worth_real: float = 0.0
    balances: dict[str, float] = field(default_factory=dict)   # account id -> EOY balance

    failed: bool = False

    def to_row(self) -> dict:
        row = {}
        for f in fields(self):
            v = getattr(self, f.name)
            if f.name == "balances":
                for acct_id, bal in v.items():
                    row[f"bal_{acct_id}"] = bal
            else:
                row[f.name] = v
        return row


@dataclass
class SimState:
    """Mutable per-path state threaded through the annual loop."""

    household: Household
    accounts: list[Account]
    cash_buffer: float = 0.0            # intra-year float; swept at year end
    capital_loss_carryforward: float = 0.0   # Schedule D carryover, nominal
    magi_history: dict[int, float] = field(default_factory=dict)   # year -> IRMAA MAGI
    failed: bool = False
    first_failure_year: int | None = None

    def account(self, acct_id: str) -> Account:
        for a in self.accounts:
            if a.id == acct_id:
                return a
        raise KeyError(f"no account {acct_id!r}")

    @property
    def net_worth(self) -> float:
        return sum(a.balance for a in self.accounts) + self.cash_buffer
