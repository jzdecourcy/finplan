from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from finplan.engine.results import SimResults  # noqa: E402


def load_snapshot_history(snap_dir: str | Path = "snapshots") -> list[tuple[int, float]]:
    """(year-fraction, nominal net worth) per dated snapshot file — the 'actuals'."""
    import datetime as dt

    import yaml

    points = []
    d = Path(snap_dir)
    if not d.exists():
        return points
    for f in sorted(d.glob("*.yaml")):
        try:
            date = dt.date.fromisoformat(f.stem)
            data = yaml.safe_load(f.read_text(encoding="utf-8")) or {}
            accounts = data.get("accounts", data)
            total = sum(
                (v.get("balance", 0.0) if isinstance(v, dict) else float(v))
                for v in accounts.values()
            )
            points.append((date.year + (date.timetuple().tm_yday / 365), total))
        except (ValueError, AttributeError):
            continue
    return points


def net_worth_chart(
    results: SimResults, out_path: str | Path,
    actuals: list[tuple[float, float]] | None = None,
) -> Path:
    """Deterministic: single line. Multi-path: percentile fan (p10-p90 bands + median).
    `actuals` (from snapshot history) plot as dots over the projection."""
    out_path = Path(out_path)
    fig, ax = plt.subplots(figsize=(10, 6))
    if results.n_paths == 1:
        df = results.ledger
        ax.plot(df["year"], df["net_worth_real"], color="#2563eb", lw=2)
    else:
        pct = results.percentiles("net_worth_real")
        years = pct.index
        ax.fill_between(years, pct["p10"], pct["p90"], color="#2563eb", alpha=0.15,
                        label="10th-90th pct")
        ax.fill_between(years, pct["p25"], pct["p75"], color="#2563eb", alpha=0.25,
                        label="25th-75th pct")
        ax.plot(years, pct["p50"], color="#2563eb", lw=2, label="median")
        ax.legend(frameon=False)
    if actuals:
        # actuals are nominal; near the start of the sim real ~ nominal, close enough
        # for eyeballing trajectory-vs-plan
        xs, ys = zip(*actuals)
        ax.scatter(xs, ys, color="#111827", zorder=5, s=28, label="actual (snapshots)")
        ax.legend(frameon=False)
    ax.set_title("Net worth (real dollars)")
    ax.set_xlabel("Year")
    ax.yaxis.set_major_formatter(lambda v, _: f"${v/1e6:.1f}M" if abs(v) >= 1e6 else f"${v/1e3:.0f}k")
    ax.axhline(0, color="#9ca3af", lw=0.8)
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    plt.close(fig)
    return out_path
