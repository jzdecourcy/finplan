"""Michigan individual income tax (MI-1040).

Flat rate on federal AGI minus Michigan subtractions. Two elective methods are evaluated
each year and the better (lower taxable income) wins — RAB 2026-1:

Method 1 — retirement subtraction (PA 4 of 2023, fully phased in 2026): pension/IRA/401k
distributions deductible up to CPI-indexed caps ($67,610 / $135,220 for 2026). The caps
apply regardless of birth year; premature (pre-59.5) distributions don't qualify.

Method 2 — senior standard deduction (MCL 206.30(9), age 67+): flat $20,000/$40,000
against all income, reduced by the personal exemption (the exemption legitimately counts
twice — RAB 2026-1 Example J), stacking with the SS subtraction per PA 24 of 2025.

Common to both: Social Security fully exempt (subtract the federally taxable portion),
MESP/529 deduction up to the cap, personal exemptions. No preferential capital-gains
rate. Roth conversions get no retirement subtraction here (conservative: conversions
usually happen pre-67 as part of a ladder; revisit if a post-67 conversion strategy
appears — see knowledge/assumptions.md).
"""

from __future__ import annotations

from finplan.taxes.types import TaxInput


def michigan_tax(
    inp: TaxInput, federal_agi: float, taxable_ss: float, params: dict, filing: str
) -> float:
    ages = list(inp.ages.values()) or [0]
    oldest = max(ages)
    # MI-1040 line 9a: one exemption per filer plus one per claimable dependent.
    n_exemptions = max(1, len(inp.ages)) + max(0, int(inp.dependents))
    exemptions = n_exemptions * params["personal_exemption"]

    # US-government-obligation interest (Treasuries, SGOV) is MI-exempt; non-Michigan
    # municipal interest is an MI ADDITION (we conservatively treat all muni interest
    # as non-MI-source — national funds are overwhelmingly out-of-state).
    common = (
        taxable_ss
        + inp.us_gov_interest
        + min(inp.mi_529_contributions, params["mesp_529_deduction"][filing])
    )
    # Sch 1 line 1: non-MI muni interest. Line 2: income taxes deducted at the entity
    # level (e.g. an S-corp's flow-through-entity or other-state tax on the K-1).
    additions = inp.tax_exempt_interest + max(0.0, inp.state_tax_addback)

    # Method 1: capped retirement subtraction
    rs = params["retirement_subtraction"]
    retirement_income = inp.traditional_distributions if oldest >= rs["min_age"] else 0.0
    method1 = common + min(retirement_income, rs[f"cap_{filing}"])

    # Method 2: senior standard deduction (67+), reduced by the personal exemption
    method2 = -1.0
    ssd = params["senior_standard_deduction"]
    if oldest >= ssd["min_age"]:
        method2 = common + max(0.0, ssd[filing] - exemptions)

    subtractions = max(method1, method2)
    taxable = max(0.0, federal_agi + additions - subtractions - exemptions)
    return params["rate"] * taxable
