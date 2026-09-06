from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from finplan.model.refs import RefContext, YearRef, resolve


@dataclass
class Event:
    """One-time cash delta in a given year.

    cash > 0 is an inflow (windfall, sale proceeds); cash < 0 an outflow (down payment,
    tuition payment). Amounts are start-year real dollars, inflated to nominal at the event
    year. Recurring consequences (new mortgage, property tax) are modeled as separate
    expense streams in the same overlay, not embedded here.
    """

    id: str
    year: YearRef
    cash: float = 0.0
    taxable_as: Literal["none", "ordinary", "ltcg"] = "none"
    education: bool = False      # outflow may be funded from a 529 tax-free
    beneficiary: str | None = None   # education events: which kid's 529 first

    def occurs_in(self, year: int, ctx: RefContext) -> bool:
        return resolve(self.year, ctx) == year
