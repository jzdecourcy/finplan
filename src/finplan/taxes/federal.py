"""Federal income tax: pure functions mirroring IRS worksheets.

Sources of logic (values live in data files, not here):
- ordinary_tax: bracket walk over the rate schedule
- ltcg_tax: Qualified Dividends and Capital Gain Tax Worksheet (stacking: preferential
  income sits ON TOP of ordinary income and fills the 0/15/20 tiers from where ordinary
  taxable income ends)
- taxable_social_security: Pub 915 provisional-income worksheet
"""

from __future__ import annotations


def bracket_tax(taxable: float, brackets: list[dict]) -> float:
    """brackets: [{upto: <threshold or null for top>, rate: r}, ...] ascending."""
    if taxable <= 0:
        return 0.0
    tax = 0.0
    lower = 0.0
    for b in brackets:
        upper = b["upto"] if b["upto"] is not None else float("inf")
        if taxable > lower:
            tax += (min(taxable, upper) - lower) * b["rate"]
            lower = upper
        else:
            break
    return tax


def ordinary_tax(taxable_ordinary: float, params: dict, filing: str) -> float:
    return bracket_tax(taxable_ordinary, params["ordinary_brackets"][filing])


def ltcg_tax(taxable_ordinary: float, pref: float, params: dict, filing: str) -> float:
    """Tax on LTCG + qualified dividends, stacked on top of ordinary taxable income."""
    if pref <= 0:
        return 0.0
    stack_bottom = max(0.0, taxable_ordinary)
    stack_top = stack_bottom + pref
    tax = 0.0
    lower = 0.0
    for b in params["ltcg_brackets"][filing]:
        upper = b["upto"] if b["upto"] is not None else float("inf")
        overlap = max(0.0, min(upper, stack_top) - max(lower, stack_bottom))
        tax += overlap * b["rate"]
        lower = upper
        if lower >= stack_top:
            break
    return tax


def taxable_social_security(
    ss_benefits: float, other_income: float, params: dict, filing: str,
    tax_exempt_interest: float = 0.0,
) -> float:
    """Pub 915 worksheet. other_income = AGI components excluding SS."""
    if ss_benefits <= 0:
        return 0.0
    base1, base2 = params["ss_taxation"][f"thresholds_{filing}"]
    provisional = other_income + tax_exempt_interest + 0.5 * ss_benefits
    if provisional <= base1:
        return 0.0
    if provisional <= base2:
        return min(0.5 * (provisional - base1), 0.5 * ss_benefits)
    tier1 = min(0.5 * (base2 - base1), 0.5 * ss_benefits)
    return min(0.85 * (provisional - base2) + tier1, 0.85 * ss_benefits)


def standard_deduction(
    params: dict, filing: str, ages: list[int], magi: float, year: int | None = None
) -> float:
    sd = params["standard_deduction"][filing]
    extra = params["standard_deduction"][f"extra_65_{filing}"]
    seniors = sum(1 for a in ages if a >= 65)
    sd += seniors * extra
    bonus_cfg = params["standard_deduction"].get("senior_bonus")
    if bonus_cfg and year is not None and year > bonus_cfg.get("expires_after", 10**9):
        bonus_cfg = None
    if bonus_cfg and seniors:
        threshold = bonus_cfg[f"magi_threshold_{filing}"]
        phased = max(0.0, bonus_cfg["amount"] - bonus_cfg["phaseout_rate"] * max(0.0, magi - threshold))
        sd += seniors * phased
    return sd


def niit(net_investment_income: float, magi: float, params: dict, filing: str) -> float:
    cfg = params["niit"]
    over = max(0.0, magi - cfg[f"threshold_{filing}"])
    return cfg["rate"] * min(max(0.0, net_investment_income), over)
