from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from finplan.model.refs import RefContext, YearRef, resolve

IncomeKind = Literal["salary", "business", "pension", "rental", "other"]


@dataclass
class _Stream:
    id: str
    annual: float                # start_year real (today's) dollars
    start: YearRef
    end: YearRef                 # inclusive
    growth_real: float = 0.0     # real growth on top of inflation

    def active_in(self, year: int, ctx: RefContext) -> bool:
        return resolve(self.start, ctx) <= year <= resolve(self.end, ctx)

    def amount_in(self, year: int, ctx: RefContext, cpi_factor: float) -> float:
        """Nominal amount for `year`. Real growth compounds from the stream's start."""
        if not self.active_in(year, ctx):
            return 0.0
        years_running = year - resolve(self.start, ctx)
        return self.annual * cpi_factor * (1.0 + self.growth_real) ** years_running


@dataclass
class IncomeStream(_Stream):
    owner: str | None = None
    kind: IncomeKind = "salary"
    taxable: bool = True
    fica: bool = True
    phantom: bool = False   # taxable, no cash (undistributed pass-through share)

    def ctx_for(self, base: RefContext) -> RefContext:
        return RefContext(base.birth_years, base.retirement_years, base.horizon_year, self.owner)


@dataclass
class ExpenseStream(_Stream):
    discretionary: bool = False
    education: bool = False      # qualified education expense -> 529-eligible
    aca: bool = False            # ACA premium: amount doubles as the PTC benchmark
