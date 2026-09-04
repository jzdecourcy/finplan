"""ACA Premium Tax Credit (IRC § 36B), Form 8962 logic. Pure functions; parameters
come from the `aca:` block of the federal data file (Rev. Proc. 2025-25 table, FPL
from the prior year's HHS guidelines — already baked into the data).

Kept float-cheap: premium_tax_credit runs inside the withdrawal gross-up loop, which
Monte Carlo executes ~1000 paths x ~50 years x up to 25 iterations.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AcaResult:
    magi: float = 0.0
    fpl: float = 0.0
    fpl_pct: float = 0.0            # ratio: 2.25 = 225% of FPL
    applicable_pct: float = 0.0     # 0.0 above the cliff
    expected_contribution: float = 0.0
    credit: float = 0.0


def federal_poverty_line(household_size: int, aca_params: dict) -> float:
    fpl = aca_params["fpl"]
    return fpl["first_person"] + fpl["additional_person"] * (household_size - 1)


def applicable_percentage(fpl_ratio: float, aca_params: dict) -> float | None:
    """Expected-contribution percentage for a household at `fpl_ratio` x FPL.
    None above the cliff (§ 36B(c)(1)(A): eligible while income "does not exceed"
    400% — so exactly 4.00 still qualifies). Linear interpolation within bands."""
    if fpl_ratio > aca_params["cliff_fpl_ratio"]:
        return None
    # Bands are half-open [from, to) — "at least 133% but less than 150%" — so a
    # boundary ratio belongs to the UPPER band (1.33 -> 3.14%, not 2.10%). The one
    # closed endpoint is the cliff itself: exactly 400% takes the last band's top.
    for band in aca_params["applicable_pct"]:
        if band["fpl_from"] <= fpl_ratio < band["fpl_to"]:
            span = band["fpl_to"] - band["fpl_from"]
            frac = (fpl_ratio - band["fpl_from"]) / span if span > 0 else 0.0
            return band["pct_from"] + frac * (band["pct_to"] - band["pct_from"])
    return aca_params["applicable_pct"][-1]["pct_to"]


def aca_magi(agi: float, tax_exempt_interest: float, ss_benefits: float,
             taxable_ss: float) -> float:
    """§ 36B(d)(2)(B): AGI + tax-exempt interest + the UNTAXED portion of Social
    Security (+ excluded foreign income, not modeled)."""
    return agi + tax_exempt_interest + max(0.0, ss_benefits - taxable_ss)


def premium_tax_credit(magi: float, household_size: int, benchmark_premium: float,
                       aca_params: dict) -> AcaResult:
    fpl = federal_poverty_line(household_size, aca_params)
    fpl_pct = magi / fpl if fpl > 0 else 0.0
    pct = applicable_percentage(fpl_pct, aca_params)
    if pct is None:
        return AcaResult(magi=magi, fpl=fpl, fpl_pct=fpl_pct)
    contribution = pct * magi
    credit = max(0.0, benchmark_premium - contribution)
    return AcaResult(
        magi=magi, fpl=fpl, fpl_pct=fpl_pct, applicable_pct=pct,
        expected_contribution=contribution, credit=credit,
    )
