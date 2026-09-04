from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402

from finplan.engine.results import SimResults  # noqa: E402

# validated reference palette, categorical slots in fixed order (see report/pdf.py)
_COLORS = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300",
           "#4a3aa7", "#e34948"]


@dataclass
class NamedResults:
    name: str
    results: SimResults


def comparison_table(runs: list[NamedResults]) -> pd.DataFrame:
    rows = []
    for r in runs:
        m = r.results.metrics()
        rows.append(
            {
                "scenario": r.name,
                "success %": round(100 * m["success_probability"], 1),
                "median terminal (real)": m["terminal_wealth_real_median"],
                "p10 terminal (real)": m["terminal_wealth_real_p10"],
                "median lifetime tax": m["median_lifetime_tax"],
                "median first failure": m["median_first_failure_year"] or "-",
            }
        )
    return pd.DataFrame(rows).set_index("scenario")


def _overlay_fig(runs: list[NamedResults]):
    """Median net-worth lines per scenario, with p10-p90 shading when multi-path."""
    fig, ax = plt.subplots(figsize=(11, 6.5))
    for i, r in enumerate(runs):
        color = _COLORS[i % len(_COLORS)]
        if r.results.n_paths == 1:
            df = r.results.ledger
            ax.plot(df["year"], df["net_worth_real"], color=color, lw=2, label=r.name)
        else:
            pct = r.results.percentiles("net_worth_real")
            ax.fill_between(pct.index, pct["p10"], pct["p90"], color=color, alpha=0.10)
            ax.plot(pct.index, pct["p50"], color=color, lw=2, label=f"{r.name} (median)")
    ax.set_title("Net worth by scenario (real dollars)")
    ax.set_xlabel("Year")
    ax.yaxis.set_major_formatter(
        lambda v, _: f"${v/1e6:.1f}M" if abs(v) >= 1e6 else f"${v/1e3:.0f}k"
    )
    ax.axhline(0, color="#9ca3af", lw=0.8)
    ax.legend(frameon=False)
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    return fig


def overlay_chart(runs: list[NamedResults], out_path: str | Path) -> Path:
    out_path = Path(out_path)
    fig = _overlay_fig(runs)
    fig.savefig(out_path, dpi=150)
    plt.close(fig)
    return out_path


def _terminal_fig(runs: list[NamedResults]):
    fig, ax = plt.subplots(figsize=(10, 6))
    for i, r in enumerate(runs):
        tw = r.results.terminal_wealth / 1e6
        if len(tw) > 1:
            ax.hist(tw, bins=60, alpha=0.45, color=_COLORS[i % len(_COLORS)], label=r.name)
        else:
            ax.axvline(tw.iloc[0], color=_COLORS[i % len(_COLORS)], lw=2, label=r.name)
    ax.set_title("Terminal wealth distribution (real $M)")
    ax.set_xlabel("Real terminal net worth ($M)")
    ax.legend(frameon=False)
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    return fig


def terminal_wealth_chart(runs: list[NamedResults], out_path: str | Path) -> Path:
    out_path = Path(out_path)
    fig = _terminal_fig(runs)
    fig.savefig(out_path, dpi=150)
    plt.close(fig)
    return out_path


def _pdf_table_page(table: pd.DataFrame, mode: str, config_notes: dict[str, str]):
    fig = plt.figure(figsize=(11, 8.5))
    fig.text(0.07, 0.9, "Scenario comparison", fontsize=18, weight="bold")
    fig.text(0.07, 0.86, f"mode: {mode}", fontsize=10, color="#52514e")
    tbl = table.reset_index()
    ax = fig.add_axes([0.05, 0.45, 0.9, 0.36])
    ax.axis("off")
    mpl_table = ax.table(
        cellText=[[f"{v:,.0f}" if isinstance(v, float) else str(v) for v in row]
                  for row in tbl.itertuples(index=False)],
        colLabels=list(tbl.columns), loc="upper center", cellLoc="right",
    )
    mpl_table.auto_set_font_size(False)
    mpl_table.set_fontsize(9)
    mpl_table.scale(1, 1.5)
    y = 0.38
    for name, note in config_notes.items():
        fig.text(0.07, y, f"{name}: {note}"[:160], fontsize=8, color="#52514e")
        y -= 0.03
    return fig


def write_pdf(
    runs: list[NamedResults], out_path: str | Path, mode: str,
    config_notes: dict[str, str],
) -> Path:
    from matplotlib.backends.backend_pdf import PdfPages

    out_path = Path(out_path)
    with PdfPages(out_path) as pdf:
        for fig in (_pdf_table_page(comparison_table(runs), mode, config_notes),
                    _overlay_fig(runs), _terminal_fig(runs)):
            pdf.savefig(fig)
            plt.close(fig)
    return out_path


def write_report(
    runs: list[NamedResults], out_dir: str | Path, mode: str, config_notes: dict[str, str]
) -> Path:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    table = comparison_table(runs)
    overlay_chart(runs, out / "overlay.png")
    terminal_wealth_chart(runs, out / "terminal_wealth.png")
    for r in runs:
        r.results.ledger.to_csv(out / f"ledger-{r.name}.csv", index=False)
    lines = [
        "# Scenario comparison",
        "",
        f"mode: **{mode}**, paths per scenario: "
        f"{', '.join(f'{r.name}={r.results.n_paths}' for r in runs)}",
        "",
        table.to_markdown(),
        "",
        "![overlay](overlay.png)",
        "",
        "![terminal wealth](terminal_wealth.png)",
        "",
        "## Scenario definitions",
    ]
    for name, note in config_notes.items():
        lines += [f"- **{name}**: {note}"]
    report = out / "report.md"
    report.write_text("\n".join(lines), encoding="utf-8")
    (out / "comparison.csv").write_text(table.to_csv(), encoding="utf-8")
    try:
        write_pdf(runs, out / "report.pdf", mode, config_notes)
    except Exception:  # PDF is best-effort; report.md + CSVs are the record
        pass
    return report
