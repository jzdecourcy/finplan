"""Programmatic entry points used by the CLI and tests."""

from __future__ import annotations

import json
from pathlib import Path

from finplan.config.loader import load_scenario
from finplan.engine.results import SimResults
from finplan.engine.runner import run as _run


def run_scenario(
    config_paths: list[str | Path],
    mode: str = "det",
    seed: int | None = None,
    n_paths: int | None = None,
    out_dir: str | Path | None = None,
) -> SimResults:
    cfg, resolved, snap_path = load_scenario(config_paths)
    results = _run(cfg, mode=mode, seed=seed, n_paths=n_paths)
    if out_dir is not None:
        out = Path(out_dir)
        out.mkdir(parents=True, exist_ok=True)
        import yaml

        (out / "resolved-config.yaml").write_text(
            yaml.safe_dump(resolved, sort_keys=False), encoding="utf-8"
        )
        results.ledger.to_csv(out / "ledger.csv", index=False)
        (out / "metrics.json").write_text(
            json.dumps(results.metrics(), indent=2), encoding="utf-8"
        )
        try:
            from finplan.report.charts import load_snapshot_history, net_worth_chart

            net_worth_chart(results, out / "net_worth.png",
                            actuals=load_snapshot_history())
        except Exception:  # charts are best-effort; the data files are the record
            pass
    return results
