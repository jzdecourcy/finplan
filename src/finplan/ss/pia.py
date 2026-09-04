"""Primary Insurance Amount (PIA) recompute from a Social Security earnings history.

Method (SSA statutory formula, today's-dollars convention):
- Historical covered earnings are wage-indexed by AWI(index year)/AWI(earnings year),
  where the index year is the year the person turns 60, capped at the latest published
  AWI year. Earnings in or after the index year enter at face value — which is exactly
  where the engine's projected future earnings (start-year real dollars) slot in.
- AIME = floor(sum of top-35 indexed years / 420).
- PIA = 90%/32%/15% of AIME across the bend points for the eligibility year (age 62),
  truncated to the next lower dime.
- Bend points derive from the 1979 bases ($180/$1,085) times AWI(eligibility-2)/AWI(1977),
  rounded to the nearest dollar. Eligibility years beyond published AWI use the latest
  derivable bend points — the "today's dollars" zero-future-wage-growth convention that
  ssa.gov estimates use, consistent with the engine's real-dollar simulation.

Only supported for people not yet eligible (under 62 at the sim start): older claimants
would need the post-62 COLA chain, and their SSA-stated benefit is better entered
directly as ss_pia_monthly.
"""

from __future__ import annotations

import math
from functools import lru_cache
from importlib import resources

import yaml

_DATA_PKG = "finplan.data.ss"
_MONTHS_IN_35_YEARS = 420


@lru_cache(maxsize=1)
def _data() -> dict:
    path = resources.files(_DATA_PKG) / "awi_series.yaml"
    return yaml.safe_load(path.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def awi_series() -> dict[int, float]:
    return {int(k): float(v) for k, v in _data()["awi"].items()}


@lru_cache(maxsize=1)
def latest_awi_year() -> int:
    return max(awi_series())


def bend_points(eligibility_year: int) -> tuple[int, int]:
    """PIA formula bend points for an eligibility year (age-62 year), whole dollars."""
    awi = awi_series()
    ref_year = min(eligibility_year - 2, latest_awi_year())
    if ref_year not in awi:
        raise ValueError(f"no AWI data to derive bend points for {eligibility_year}")
    factor = awi[ref_year] / awi[1977]
    b1, b2 = _data()["bend_point_bases_1979"]
    return round(b1 * factor), round(b2 * factor)


def compute_aime(earnings_by_year: dict[int, float], birth_year: int) -> int:
    """Average indexed monthly earnings: top 35 wage-indexed years, floored to $1."""
    awi = awi_series()
    index_year = min(birth_year + 60, latest_awi_year())
    indexed = []
    for year, amount in earnings_by_year.items():
        if year < index_year:
            if year not in awi:
                raise ValueError(f"earnings year {year} predates the AWI series")
            indexed.append(amount * awi[index_year] / awi[year])
        else:
            indexed.append(float(amount))
    top35 = sorted(indexed, reverse=True)[:35]
    return int(sum(top35) / _MONTHS_IN_35_YEARS)


def compute_pia_monthly(earnings_by_year: dict[int, float], birth_year: int) -> float:
    """Monthly PIA in index-year (~today's) dollars, truncated to the lower dime."""
    aime = compute_aime(earnings_by_year, birth_year)
    bp1, bp2 = bend_points(birth_year + 62)
    r1, r2, r3 = _data()["pia_rates"]
    pia = (
        r1 * min(aime, bp1)
        + r2 * max(0, min(aime, bp2) - bp1)
        + r3 * max(0, aime - bp2)
    )
    return math.floor(pia * 10 + 1e-9) / 10
