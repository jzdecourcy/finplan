"""Multi-page PDF report for a single scenario run.

Built entirely with matplotlib's PdfPages — no new dependencies. Pages:
  1. headline metrics (stat tiles + run metadata)
  2. net worth fan chart (with snapshot actuals when available)
  3. where the money comes from / goes (funding sources vs outflow)
  4. account balances by tax bucket
  5. taxes by component + forced/elective distributions
  6. annual summary table

Monte Carlo runs chart the per-year MEDIAN of each component independently;
components therefore need not sum exactly to the median total (noted on-page).

Colors follow the validated reference palette (dataviz method): categorical slots
in fixed order per entity, recessive grid/axes, ink for text — never series color.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402
from matplotlib.backends.backend_pdf import PdfPages  # noqa: E402

from finplan.config.schema import ScenarioConfig  # noqa: E402
from finplan.engine.results import SimResults  # noqa: E402

# reference palette (light mode) — slots assigned per entity, in validated order
_SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300",
           "#4a3aa7", "#e34948"]
_TYPE_COLORS = {  # account tax buckets: fixed slot per type, never re-ranked
    "taxable": _SERIES[0], "traditional": _SERIES[1], "roth": _SERIES[2],
    "cash": _SERIES[3], "hsa": _SERIES[4], "529": _SERIES[5],
}
_INK, _INK2, _MUTED = "#0b0b0b", "#52514e", "#898781"
_GRID, _BASELINE, _SURFACE = "#e1e0d9", "#c3c2b7", "#fcfcfb"
_CRITICAL = "#d03b3b"   # status color: failure markers only, never a series

_PAGE = (11, 8.5)       # US letter landscape


def _fmt_dollars(v: float, _pos=None) -> str:
    if abs(v) >= 1e6:
        return f"${v/1e6:.1f}M"
    return f"${v/1e3:.0f}k"


def _style_axes(ax) -> None:
    ax.set_facecolor(_SURFACE)
    ax.spines[["top", "right"]].set_visible(False)
    ax.spines["left"].set_color(_BASELINE)
    ax.spines["bottom"].set_color(_BASELINE)
    ax.tick_params(colors=_MUTED, labelsize=9)
    ax.yaxis.grid(True, color=_GRID, lw=0.8)
    ax.set_axisbelow(True)


def _new_page(title: str, caption: str = ""):
    fig, ax = plt.subplots(figsize=_PAGE)
    fig.patch.set_facecolor(_SURFACE)
    fig.suptitle(title, x=0.07, ha="left", fontsize=15, color=_INK, weight="bold")
    if caption:
        fig.text(0.07, 0.935, caption, fontsize=9, color=_INK2)
    fig.subplots_adjust(top=0.88, left=0.07, right=0.95, bottom=0.09)
    _style_axes(ax)
    return fig, ax


def _median_by_year(results: SimResults, col: str) -> pd.Series:
    return results.ledger.groupby("year")[col].median()


def _mc_note(results: SimResults) -> str:
    if results.n_paths == 1:
        return ""
    return (f"per-year medians across {results.n_paths} simulated paths; "
            f"components may not sum exactly to totals")


# --- pages ---


def _summary_page(pdf: PdfPages, results: SimResults, cfg: ScenarioConfig) -> None:
    m = results.metrics()
    fig = plt.figure(figsize=_PAGE)
    fig.patch.set_facecolor(_SURFACE)
    fig.text(0.07, 0.88, cfg.meta.name, fontsize=24, color=_INK, weight="bold")
    if cfg.meta.description:
        fig.text(0.07, 0.83, cfg.meta.description, fontsize=12, color=_INK2)
    meta = (f"mode {m['mode']}  ·  paths {m['n_paths']}"
            + (f"  ·  seed {m['seed']}" if m["seed"] is not None else "")
            + f"  ·  generated {dt.date.today().isoformat()}")
    fig.text(0.07, 0.78, meta, fontsize=10, color=_MUTED)

    tiles = [
        ("Success", f"{100 * m['success_probability']:.1f}%"),
        ("Median terminal (real)", _fmt_dollars(m["terminal_wealth_real_median"])),
        ("p10 terminal (real)", _fmt_dollars(m["terminal_wealth_real_p10"])),
        ("Median lifetime tax", _fmt_dollars(m["median_lifetime_tax"])),
        ("Median first failure", str(m["median_first_failure_year"] or "none")),
    ]
    for i, (label, value) in enumerate(tiles):
        x = 0.07 + (i % 3) * 0.31
        y = 0.55 - (i // 3) * 0.24
        fig.text(x, y, value, fontsize=26, color=_INK)
        fig.text(x, y - 0.055, label.upper(), fontsize=9, color=_MUTED)
    pdf.savefig(fig)
    plt.close(fig)


def _net_worth_page(
    pdf: PdfPages, results: SimResults,
    actuals: list[tuple[float, float]] | None,
) -> None:
    fig, ax = _new_page("Net worth (real dollars)")
    if results.n_paths == 1:
        df = results.ledger
        ax.plot(df["year"], df["net_worth_real"], color=_SERIES[0], lw=2)
    else:
        pct = results.percentiles("net_worth_real")
        ax.fill_between(pct.index, pct["p10"], pct["p90"], color=_SERIES[0],
                        alpha=0.15, label="10th–90th pct")
        ax.fill_between(pct.index, pct["p25"], pct["p75"], color=_SERIES[0],
                        alpha=0.25, label="25th–75th pct")
        ax.plot(pct.index, pct["p50"], color=_SERIES[0], lw=2, label="median")
    if actuals:
        xs, ys = zip(*actuals)
        ax.scatter(xs, ys, color=_INK, zorder=5, s=28, label="actual (snapshots)")
    ffy = results.metrics()["median_first_failure_year"]
    if ffy:
        ax.axvline(ffy, color=_CRITICAL, lw=1.2, ls="--",
                   label=f"median first failure ({ffy})")
    ax.axhline(0, color=_BASELINE, lw=0.8)
    ax.yaxis.set_major_formatter(_fmt_dollars)
    if ax.get_legend_handles_labels()[0]:
        ax.legend(frameon=False, labelcolor=_INK2, fontsize=9)
    pdf.savefig(fig)
    plt.close(fig)


def _funding_page(pdf: PdfPages, results: SimResults) -> None:
    fig, ax = _new_page("Where the money comes from", _mc_note(results))
    years = sorted(results.ledger["year"].unique())
    sources = [  # income first, then portfolio draws — fixed slot order
        ("wages", "Wages"), ("other_income", "Other income"),
        ("ss_benefits", "Social Security"), ("withdrawals_total", "Withdrawals"),
    ]
    stacks = [_median_by_year(results, col).reindex(years).fillna(0.0)
              for col, _ in sources]
    ax.stackplot(years, stacks, labels=[label for _, label in sources],
                 colors=_SERIES[:len(sources)], edgecolor=_SURFACE, linewidth=1)
    outflow = (_median_by_year(results, "spending")
               + _median_by_year(results, "tax_total")).reindex(years)
    ax.plot(years, outflow, color=_INK, lw=2, label="Spending + taxes")
    ax.yaxis.set_major_formatter(_fmt_dollars)
    ax.legend(frameon=False, labelcolor=_INK2, fontsize=9, loc="upper left")
    pdf.savefig(fig)
    plt.close(fig)


def _balances_page(pdf: PdfPages, results: SimResults, cfg: ScenarioConfig) -> None:
    fig, ax = _new_page("Account balances by tax bucket (nominal)", _mc_note(results))
    years = sorted(results.ledger["year"].unique())
    by_type: dict[str, pd.Series] = {}
    for a in cfg.accounts:
        col = f"bal_{a.id}"
        if col not in results.ledger.columns:
            continue
        s = _median_by_year(results, col).reindex(years).fillna(0.0)
        by_type[a.type] = by_type.get(a.type, 0.0) + s
    types = [t for t in _TYPE_COLORS if t in by_type]   # fixed palette order
    ax.stackplot(years, [by_type[t] for t in types], labels=types,
                 colors=[_TYPE_COLORS[t] for t in types],
                 edgecolor=_SURFACE, linewidth=1)
    ax.yaxis.set_major_formatter(_fmt_dollars)
    ax.legend(frameon=False, labelcolor=_INK2, fontsize=9, loc="upper left")
    pdf.savefig(fig)
    plt.close(fig)


def _tax_page(pdf: PdfPages, results: SimResults) -> None:
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=_PAGE, height_ratios=[3, 2])
    fig.patch.set_facecolor(_SURFACE)
    fig.suptitle("Taxes and forced / elective distributions", x=0.07, ha="left",
                 fontsize=15, color=_INK, weight="bold")
    note = _mc_note(results)
    if note:
        fig.text(0.07, 0.935, note, fontsize=9, color=_INK2)
    fig.subplots_adjust(top=0.88, left=0.07, right=0.95, bottom=0.08, hspace=0.35)
    for ax in (ax1, ax2):
        _style_axes(ax)
    years = sorted(results.ledger["year"].unique())

    parts = [("tax_federal", "Federal"), ("tax_state", "State"),
             ("tax_fica", "FICA")]
    colors = list(_SERIES[:3])
    penalties = _median_by_year(results, "tax_penalties").reindex(years).fillna(0.0)
    stacks = [_median_by_year(results, col).reindex(years).fillna(0.0)
              for col, _ in parts]
    labels = [label for _, label in parts]
    if penalties.sum() > 0:
        stacks.append(penalties)
        labels.append("Early-withdrawal penalties")
        colors.append(_SERIES[7])
    ax1.stackplot(years, stacks, labels=labels, colors=colors,
                  edgecolor=_SURFACE, linewidth=1)
    ax1.set_title("Annual tax by component", loc="left", fontsize=11, color=_INK2)
    ax1.yaxis.set_major_formatter(_fmt_dollars)
    ax1.legend(frameon=False, labelcolor=_INK2, fontsize=9, loc="upper left")

    dists = [("rmd", "RMDs"), ("sepp", "72(t) SEPP"),
             ("roth_conversion", "Roth conversions")]
    plotted = False
    for i, (col, label) in enumerate(dists):
        s = _median_by_year(results, col).reindex(years).fillna(0.0)
        if s.sum() > 0:
            ax2.plot(years, s, color=_SERIES[i], lw=2, label=label)
            plotted = True
    ax2.set_title("Forced / elective distributions", loc="left", fontsize=11,
                  color=_INK2)
    ax2.yaxis.set_major_formatter(_fmt_dollars)
    if plotted:
        ax2.legend(frameon=False, labelcolor=_INK2, fontsize=9, loc="upper left")
    else:
        ax2.text(0.5, 0.5, "none in this scenario", transform=ax2.transAxes,
                 ha="center", color=_MUTED, fontsize=10)
    pdf.savefig(fig)
    plt.close(fig)


def _table_page(pdf: PdfPages, results: SimResults, every: int = 5) -> None:
    cols = [("year", "Year", "{:.0f}"), ("wages", "Wages", "{:,.0f}"),
            ("ss_benefits", "SocSec", "{:,.0f}"), ("spending", "Spending", "{:,.0f}"),
            ("tax_total", "Taxes", "{:,.0f}"),
            ("withdrawals_total", "Withdrawn", "{:,.0f}"),
            ("contributions_total", "Saved", "{:,.0f}"),
            ("net_worth_real", "NW (real)", "{:,.0f}")]
    med = results.ledger.groupby("year")[[c for c, _, _ in cols[1:]]].median()
    med = med[med.index % every == 0]
    fig = plt.figure(figsize=_PAGE)
    fig.patch.set_facecolor(_SURFACE)
    title = "Annual summary" + ("" if results.n_paths == 1
                                else " (per-year medians)")
    fig.text(0.07, 0.93, title, fontsize=15, color=_INK, weight="bold")
    cell_rows = [
        [f"{int(year)}"] + [fmt.format(med.loc[year, col])
                            for col, _, fmt in cols[1:]]
        for year in med.index
    ]
    ax = fig.add_axes([0.05, 0.06, 0.9, 0.82])
    ax.axis("off")
    table = ax.table(cellText=cell_rows, colLabels=[h for _, h, _ in cols],
                     loc="upper center", cellLoc="right")
    table.auto_set_font_size(False)
    table.set_fontsize(9)
    table.scale(1, 1.35)
    for (row, _col), cell in table.get_celld().items():
        cell.set_edgecolor(_GRID)
        cell.set_text_props(color=_INK if row else _INK2,
                            weight="normal" if row else "bold")
    pdf.savefig(fig)
    plt.close(fig)


def write_pdf_report(
    results: SimResults,
    cfg: ScenarioConfig,
    out_path: str | Path,
    actuals: list[tuple[float, float]] | None = None,
) -> Path:
    out_path = Path(out_path)
    with PdfPages(out_path) as pdf:
        _summary_page(pdf, results, cfg)
        _net_worth_page(pdf, results, actuals)
        _funding_page(pdf, results)
        _balances_page(pdf, results, cfg)
        _tax_page(pdf, results)
        _table_page(pdf, results)
        pdf.infodict()["Title"] = f"finplan report — {cfg.meta.name}"
    return out_path
