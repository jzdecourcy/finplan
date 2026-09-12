"""Shared tax input/result types. The simulator assembles TaxInput; a TaxEngine prices it.

Phase 1 ships a flat-rate stub engine; Phase 2 replaces it with the real federal+state
pipeline behind the same interface.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from finplan.model.household import FilingStatus


@dataclass
class TaxInput:
    year: int
    filing_status: FilingStatus
    ages: dict[str, int] = field(default_factory=dict)     # person name -> age this year
    cpi_factor: float = 1.0        # cumulative inflation since sim start (bracket indexing)

    # ordinary income components (nominal dollars)
    wages: float = 0.0             # per-person split only matters for FICA; see wages_by_person
    wages_by_person: dict[str, float] = field(default_factory=dict)
    business: float = 0.0
    other_ordinary: float = 0.0    # pension, rental, non-qualified 529/HSA earnings, etc.
    interest: float = 0.0
    us_gov_interest: float = 0.0   # Treasury/SGOV: federally taxable, MI-exempt
    tax_exempt_interest: float = 0.0  # muni: federal-exempt, in SS provisional income;
                                      # non-MI munis are ADDED BACK on the MI return
    ordinary_dividends: float = 0.0
    traditional_distributions: float = 0.0    # includes RMDs
    roth_conversions: float = 0.0
    ss_benefits: float = 0.0       # gross benefits; engine determines taxable share

    # preferential-rate components
    qualified_dividends: float = 0.0
    realized_ltcg: float = 0.0
    realized_stcg: float = 0.0
    capital_loss_carryforward: float = 0.0  # prior years' unused capital loss (positive)
    sec199a_dividends: float = 0.0  # REIT/PTP dividends (1099-DIV box 5): a SUBSET of
                                    # ordinary_dividends that also earns the 20% QBI deduction
    foreign_tax_paid: float = 0.0   # 1099-DIV box 7: creditable against federal tax

    # penalties / state hooks
    penalty_base: float = 0.0      # early-withdrawal amounts (10% federal)
    mi_529_contributions: float = 0.0
    dependents: int = 0            # claimable dependents: MI personal exemptions only
                                   # (the federal child credit is phased out at the incomes
                                   # this engine targets; not modeled)
    state_tax_addback: float = 0.0 # MI Sch 1 line 2: income taxes deducted at the entity
                                   # level on a K-1, added back on the MI return
    # QBI (s199A): business income is presumed qualified; deduction limited by
    # min(20% x QBI, wage cap, 20% x (taxable income - net cap gain/qdiv)).
    qbi_wage_cap: float | None = None   # None disables the deduction

    # ACA premium tax credit (§ 36B); both must be > 0 to activate
    aca_benchmark_premium: float = 0.0  # nominal benchmark (SLCSP proxy) this year
    aca_household_size: int = 0         # tax-family size for the FPL denominator

    # Medicare IRMAA (§ 1839(i)); active when medicare_enrollees > 0
    medicare_enrollees: int = 0         # people on Medicare Part B/D this year
    irmaa_magi: float | None = None     # MAGI from the two-years-back return (nominal);
                                        # None -> fall back to THIS year's MAGI

    @property
    def ordinary_total(self) -> float:
        return (
            self.wages + self.business + self.other_ordinary + self.interest
            + self.us_gov_interest + self.ordinary_dividends
            + self.traditional_distributions + self.roth_conversions
            + self.realized_stcg
        )


@dataclass
class TaxResult:
    total: float = 0.0
    federal: float = 0.0
    state: float = 0.0
    fica: float = 0.0
    penalties: float = 0.0
    agi: float = 0.0
    taxable_income: float = 0.0
    taxable_ss: float = 0.0
    qbi_deduction: float = 0.0
    marginal_rate_ordinary: float = 0.0
    marginal_rate_ltcg: float = 0.0
    aca_magi: float = 0.0
    aca_fpl_pct: float = 0.0    # ratio (2.25 = 225% FPL); 0 when ACA inactive
    aca_credit: float = 0.0
    niit: float = 0.0
    foreign_tax_credit: float = 0.0
    capital_loss_carryforward_out: float = 0.0   # unused loss carried to next year
    magi_irmaa: float = 0.0     # AGI + tax-exempt interest: drives IRMAA two years on
    irmaa: float = 0.0          # annual Part B + D surcharge, all enrollees (in total)
    irmaa_tier: int = 0         # 0 = none, 1..5


class TaxEngine(Protocol):
    def compute(self, inp: TaxInput) -> TaxResult: ...


class FlatTaxStub:
    """Phase-1 placeholder: flat effective rate on ordinary income, 15% on LTCG/QDIV,
    7.65% employee FICA on wages, 85% of SS treated as ordinary. Replaced in Phase 2."""

    def __init__(self, effective_rate: float):
        self.rate = effective_rate

    def compute(self, inp: TaxInput) -> TaxResult:
        ordinary = inp.ordinary_total + 0.85 * inp.ss_benefits
        pref = inp.realized_ltcg + inp.qualified_dividends
        federal = self.rate * ordinary + 0.15 * max(0.0, pref)
        fica = 0.0765 * inp.wages
        penalties = 0.10 * inp.penalty_base
        return TaxResult(
            total=federal + fica + penalties,
            federal=federal,
            fica=fica,
            penalties=penalties,
            agi=ordinary + pref,
            taxable_income=ordinary + pref,
            marginal_rate_ordinary=self.rate,
            marginal_rate_ltcg=0.15,
        )
