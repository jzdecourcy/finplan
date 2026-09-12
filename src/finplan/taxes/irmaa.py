"""Medicare income-related monthly adjustment amounts (IRMAA), SSA § 1839(i) /
42 U.S.C. § 1395r(i). Pure functions; parameters come from the `irmaa:` block of the
federal data file (CMS annual Part B / Part D announcement).

IRMAA is not a tax on the return, but it is a MAGI-driven cash outflow the plan must
fund, so the engine folds it into TaxResult.total. MAGI here is AGI plus tax-exempt
interest, and Social Security looks it up from the return filed two years earlier —
the simulator supplies that lagged figure; the engine only prices it.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class IrmaaResult:
    tier: int = 0            # 0 = standard premium, 1..5 = surcharge tiers
    monthly_part_b: float = 0.0
    monthly_part_d: float = 0.0
    annual_total: float = 0.0   # all enrollees, both parts, 12 months


def irmaa_tier(magi: float, thresholds: list[float]) -> int:
    """Tier index for `magi`. CMS words tiers 1-4 as 'greater than X' and the top
    tier as 'greater than OR EQUAL TO the last threshold', so a MAGI exactly on a
    lower threshold stays below it while one exactly on the top threshold enters it."""
    tier = 0
    last = len(thresholds) - 1
    for i, t in enumerate(thresholds):
        if (magi >= t) if i == last else (magi > t):
            tier = i + 1
    return tier


def irmaa_surcharge(magi: float, enrollees: int, filing: str, params: dict) -> IrmaaResult:
    if enrollees <= 0:
        return IrmaaResult()
    thresholds = params["tiers_mfj"] if filing == "mfj" else params["tiers_single"]
    tier = irmaa_tier(magi, thresholds)
    if tier == 0:
        return IrmaaResult()
    b = float(params["part_b_monthly_adjustment"][tier - 1])
    d = float(params["part_d_monthly_adjustment"][tier - 1])
    return IrmaaResult(
        tier=tier, monthly_part_b=b, monthly_part_d=d,
        annual_total=12.0 * (b + d) * enrollees,
    )
