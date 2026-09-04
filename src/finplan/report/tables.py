from __future__ import annotations

import pandas as pd

from finplan.engine.results import SimResults

_SUMMARY_COLS = [
    ("year", "Year", "{:d}"),
    ("wages", "Wages", "{:,.0f}"),
    ("other_income", "OtherInc", "{:,.0f}"),
    ("ss_benefits", "SocSec", "{:,.0f}"),
    ("spending", "Spending", "{:,.0f}"),
    ("tax_total", "Taxes", "{:,.0f}"),
    ("withdrawals_total", "Withdrawn", "{:,.0f}"),
    ("contributions_total", "Saved", "{:,.0f}"),
    ("net_worth", "NetWorth", "{:,.0f}"),
    ("net_worth_real", "NW(real)", "{:,.0f}"),
]


def annual_summary(results: SimResults, path: int = 0, every: int = 1) -> str:
    """Human-readable annual ledger for one path (deterministic runs: path 0)."""
    df = results.ledger[results.ledger["path"] == path]
    df = df[df["year"] % every == 0] if every > 1 else df
    with pd.option_context("display.max_rows", None):
        out = pd.DataFrame(
            {header: df[col].map(fmt.format) for col, header, fmt in _SUMMARY_COLS}
        )
        failed = df[df["failed"]]
        table = out.to_string(index=False)
        if not failed.empty:
            table += f"\n\n!! plan fails to fund spending starting {int(failed['year'].min())}"
        return table
