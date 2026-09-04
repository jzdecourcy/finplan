"""Roth conversion policies.

fill_bracket: convert enough traditional -> Roth to bring taxable ORDINARY income up to
the top of the target bracket (e.g. bracket_top=0.12). Runs after wages/RMDs are known,
so the headroom calculation is honest. Requires the real tax engine (needs brackets).

fill_to_magi: fill_bracket plus a MAGI ceiling — the subsidy-aware ladder. ACA MAGI
rises exactly $1 per $1 of conversion (AGI gains conversion + delta-taxable-SS, but
untaxed SS falls by the same delta, so the SS shift cancels), so the cap needs no
iteration: headroom = cap - MAGI(conversion=0). With magi_cap "aca_cliff" the cap is
margin x cliff_ratio x FPL(household size) from the indexed params; in years with no
ACA coverage (no benchmark premium in the TaxInput) the cap is skipped entirely.
"""

from __future__ import annotations

from finplan.config.schema import RothConversionPolicyCfg
from finplan.model.accounts import AccountType
from finplan.model.refs import RefContext, resolve
from finplan.model.state import SimState
from finplan.taxes.types import TaxInput


class RothConversionPolicy:
    def __init__(self, cfg: RothConversionPolicyCfg):
        self.cfg = cfg

    def _active(self, year: int, ctx: RefContext) -> bool:
        if self.cfg.type == "none":
            return False
        start = resolve(self.cfg.start, ctx) if self.cfg.start is not None else -10**9
        end = resolve(self.cfg.end, ctx) if self.cfg.end is not None else 10**9
        return start <= year <= end

    def conversion_amount(
        self, year: int, ctx: RefContext, state: SimState, tax_engine, inp: TaxInput
    ) -> float:
        if not self._active(year, ctx):
            return 0.0
        available = sum(
            a.balance for a in state.accounts if a.type is AccountType.TRADITIONAL
        )
        if available <= 0:
            return 0.0
        if self.cfg.type == "fixed":
            return min(self.cfg.amount * inp.cpi_factor, available)
        # fill_bracket / fill_to_magi
        if not hasattr(tax_engine, "params_for_year"):
            raise ValueError(
                f"roth_conversion {self.cfg.type} requires the us_federal tax regime"
            )
        fed_params, _ = tax_engine.params_for_year(inp.cpi_factor)
        filing = inp.filing_status.value
        brackets = fed_params["ordinary_brackets"][filing]
        bracket_top = next(
            (b["upto"] for b in brackets if abs(b["rate"] - self.cfg.bracket_top) < 1e-9),
            None,
        )
        if bracket_top is None:
            raise ValueError(f"no {self.cfg.bracket_top:.0%} bracket in {filing} schedule")
        def taxable_ordinary_with(conversion: float) -> float:
            from dataclasses import replace

            r = tax_engine.compute(
                replace(inp, roth_conversions=inp.roth_conversions + conversion)
            )
            pref = max(0.0, inp.qualified_dividends + inp.realized_ltcg)
            return max(0.0, r.taxable_income - min(pref, r.taxable_income))

        conv = min(max(0.0, bracket_top - taxable_ordinary_with(0.0)), available)
        # converting can raise taxable SS (provisional income), so refine to the top:
        for _ in range(5):
            overshoot = taxable_ordinary_with(conv) - bracket_top
            if abs(overshoot) <= 1.0 or conv <= 0:
                break
            conv = min(max(0.0, conv - overshoot), available)
        if self.cfg.type == "fill_to_magi":
            conv = min(conv, self._magi_headroom(tax_engine, fed_params, inp))
        return conv

    def _magi_headroom(self, tax_engine, fed_params: dict, inp: TaxInput) -> float:
        """Room under the MAGI cap before any conversion. ACA MAGI moves 1:1 with
        conversions (see module docstring), so no refinement loop is needed."""
        if self.cfg.magi_cap == "aca_cliff":
            aca_p = fed_params.get("aca")
            if aca_p is None or inp.aca_household_size <= 0 or inp.aca_benchmark_premium <= 0:
                return float("inf")   # no ACA coverage this year: bracket fill only
            from finplan.taxes.aca import federal_poverty_line  # noqa: PLC0415

            fpl = federal_poverty_line(inp.aca_household_size, aca_p)
            cap = self.cfg.margin * aca_p["cliff_fpl_ratio"] * fpl
        else:
            cap = self.cfg.magi_cap * inp.cpi_factor
        r0 = tax_engine.compute(inp)
        magi0 = r0.agi + inp.tax_exempt_interest + max(0.0, inp.ss_benefits - r0.taxable_ss)
        return max(0.0, cap - magi0)

    @staticmethod
    def execute(amount: float, state: SimState) -> float:
        """Move `amount` traditional -> Roth. Returns the amount actually converted."""
        if amount <= 0:
            return 0.0
        roth_targets = [a for a in state.accounts if a.type is AccountType.ROTH]
        if not roth_targets:
            return 0.0
        target = roth_targets[0]
        converted = 0.0
        for acct in state.accounts:
            if acct.type is not AccountType.TRADITIONAL or amount <= 0:
                continue
            take = min(acct.balance, amount)
            acct.balance -= take
            # conversion principal becomes Roth basis (5-year clock not modeled; noted
            # in knowledge/assumptions.md)
            target.balance += take
            target.cost_basis += take
            converted += take
            amount -= take
        return converted
