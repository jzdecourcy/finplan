"""Employee-side FICA: Social Security up to the wage base, Medicare, Additional Medicare.

The Additional Medicare 0.9% threshold applies to COMBINED wages for MFJ (employers
withhold per-person over $200k, but liability is settled on the return at the household
threshold — we model the liability)."""

from __future__ import annotations


def fica_tax(wages_by_person: dict[str, float], params: dict, filing: str) -> float:
    cfg = params["fica"]
    tax = 0.0
    for wages in wages_by_person.values():
        tax += cfg["ss_rate"] * min(wages, cfg["ss_wage_base"])
        tax += cfg["medicare_rate"] * wages
    combined = sum(wages_by_person.values())
    addl = cfg["addl_medicare"]
    tax += addl["rate"] * max(0.0, combined - addl[f"threshold_{filing}"])
    return tax
