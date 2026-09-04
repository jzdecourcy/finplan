"""The authoritative per-year tax computation: federal + FICA + penalties + state.

Pipeline (each step a pure function in this package, individually golden-tested):
  income assembly -> taxable SS (Pub 915) -> AGI -> standard deduction ->
  ordinary/preferential split -> bracket tax + LTCG stacking -> NIIT ->
  ACA premium tax credit (refundable; active only when TaxInput carries a benchmark
  premium + household size) -> FICA -> early-withdrawal penalties -> Michigan (optional)
"""

from __future__ import annotations

from dataclasses import replace

from finplan.taxes import aca as aca_mod
from finplan.taxes import federal as fed
from finplan.taxes.fica import fica_tax
from finplan.taxes.params import index_params, load_federal, load_michigan
from finplan.taxes.state.michigan import michigan_tax
from finplan.taxes.types import TaxInput, TaxResult

_CAP_LOSS_LIMIT = 3000.0  # annual capital-loss offset against ordinary income


def compute_year_tax(inp: TaxInput, params: dict, mi_params: dict | None = None) -> TaxResult:
    filing = inp.filing_status.value
    ages = list(inp.ages.values())

    net_gains = inp.realized_ltcg + inp.realized_stcg
    if net_gains >= 0:
        stcg_ordinary = max(0.0, inp.realized_stcg)
        ltcg_net = net_gains - stcg_ordinary
        loss_offset = 0.0
    else:
        stcg_ordinary = 0.0
        ltcg_net = 0.0
        loss_offset = min(_CAP_LOSS_LIMIT, -net_gains)  # no carryforward modeled

    ordinary_pre_ss = (
        inp.wages + inp.business + inp.other_ordinary + inp.interest
        + inp.us_gov_interest + inp.ordinary_dividends + inp.traditional_distributions
        + inp.roth_conversions + stcg_ordinary - loss_offset
    )
    pref = inp.qualified_dividends + ltcg_net

    other_income_for_ss = ordinary_pre_ss + pref
    taxable_ss = fed.taxable_social_security(
        inp.ss_benefits, other_income_for_ss, params, filing,
        tax_exempt_interest=inp.tax_exempt_interest,
    )

    agi = ordinary_pre_ss + pref + taxable_ss
    magi = agi  # close enough absent foreign-income addbacks
    deduction = fed.standard_deduction(params, filing, ages, magi, year=inp.year)
    taxable_before_qbi = max(0.0, agi - deduction)
    # QBI (s199A, permanent post-OBBBA): federal-only, below-the-line
    qbi_deduction = 0.0
    if inp.qbi_wage_cap is not None and inp.business > 0:
        income_limit = 0.20 * max(0.0, taxable_before_qbi - pref)
        qbi_deduction = min(0.20 * inp.business, inp.qbi_wage_cap, income_limit)
    taxable_income = max(0.0, taxable_before_qbi - qbi_deduction)
    pref_taxable = min(pref, taxable_income)
    taxable_ordinary = taxable_income - pref_taxable

    federal_tax = (
        fed.ordinary_tax(taxable_ordinary, params, filing)
        + fed.ltcg_tax(taxable_ordinary, pref_taxable, params, filing)
    )
    # NIIT: taxable interest (Treasury included) and dividends/gains; muni excluded
    nii = (
        inp.interest + inp.us_gov_interest + inp.ordinary_dividends
        + inp.qualified_dividends + max(0.0, net_gains)
    )
    federal_tax += fed.niit(nii, magi, params, filing)

    # ACA premium tax credit (§ 36B): refundable, so federal_tax may go NEGATIVE —
    # safe downstream: the withdrawal gross-up loop treats lower tax as a smaller
    # required withdrawal, and the simulator's surplus routing banks the excess.
    aca_res = None
    if inp.aca_benchmark_premium > 0 and inp.aca_household_size > 0:
        magi_aca = aca_mod.aca_magi(
            agi, inp.tax_exempt_interest, inp.ss_benefits, taxable_ss
        )
        aca_res = aca_mod.premium_tax_credit(
            magi_aca, inp.aca_household_size, inp.aca_benchmark_premium, params["aca"]
        )
        federal_tax -= aca_res.credit

    wages_by_person = inp.wages_by_person or ({"_": inp.wages} if inp.wages else {})
    fica = fica_tax(wages_by_person, params, filing) if wages_by_person else 0.0
    penalties = params["penalties"]["early_withdrawal_rate"] * inp.penalty_base

    state_tax = 0.0
    if mi_params is not None:
        state_tax = michigan_tax(inp, agi, taxable_ss, mi_params, filing)

    return TaxResult(
        total=federal_tax + fica + penalties + state_tax,
        federal=federal_tax,
        state=state_tax,
        fica=fica,
        penalties=penalties,
        agi=agi,
        taxable_income=taxable_income,
        taxable_ss=taxable_ss,
        aca_magi=aca_res.magi if aca_res else 0.0,
        aca_fpl_pct=aca_res.fpl_pct if aca_res else 0.0,
        aca_credit=aca_res.credit if aca_res else 0.0,
    )


def marginal_rate(
    inp: TaxInput, params: dict, mi_params: dict | None, kind: str = "ordinary",
    delta: float = 100.0,
) -> float:
    """Effective marginal rate on the next `delta` dollars of ordinary income or LTCG.
    Captures bracket position plus interaction effects (SS phase-in, NIIT, MI)."""
    base = compute_year_tax(inp, params, mi_params)
    if kind == "ordinary":
        probed = replace(inp, other_ordinary=inp.other_ordinary + delta)
    elif kind == "ltcg":
        probed = replace(inp, realized_ltcg=inp.realized_ltcg + delta)
    else:
        raise ValueError(f"unknown kind {kind!r}")
    bumped = compute_year_tax(probed, params, mi_params)
    fica_delta = 0.0  # income probes here are non-wage
    return (bumped.total - base.total - fica_delta) / delta


class FederalStateTaxEngine:
    """TaxEngine implementation: indexes params to each path-year's cumulative inflation."""

    def __init__(self, base_year: int, state: str = "none"):
        self.base_year = base_year
        self.state = state
        self._federal_base = load_federal(base_year)
        self._mi_base = load_michigan(base_year) if state == "michigan" else None
        self._cache: dict[tuple, tuple] = {}

    @classmethod
    def from_config(cls, tax_cfg) -> "FederalStateTaxEngine":
        return cls(base_year=tax_cfg.base_params_year, state=tax_cfg.state)

    def _params_for(self, cpi_factor: float) -> tuple[dict, dict | None]:
        key = round(cpi_factor, 3)
        if key not in self._cache:
            fed_p = index_params(self._federal_base, key, "us_federal")
            mi_p = (
                index_params(self._mi_base, key, "us_mi") if self._mi_base is not None else None
            )
            self._cache[key] = (fed_p, mi_p)
        return self._cache[key]

    def compute(self, inp: TaxInput) -> TaxResult:
        # Marginal probes are NOT computed here: compute() sits inside the gross-up loop
        # and must stay cheap. The simulator calls marginals() once per year for the ledger.
        fed_p, mi_p = self._params_for(inp.cpi_factor)
        return compute_year_tax(inp, fed_p, mi_p)

    def marginals(self, inp: TaxInput) -> tuple[float, float]:
        fed_p, mi_p = self._params_for(inp.cpi_factor)
        return (
            marginal_rate(inp, fed_p, mi_p, "ordinary"),
            marginal_rate(inp, fed_p, mi_p, "ltcg"),
        )

    def params_for_year(self, cpi_factor: float) -> tuple[dict, dict | None]:
        """Exposed for policies (bracket-fill Roth conversions) in Phase 3."""
        return self._params_for(cpi_factor)
