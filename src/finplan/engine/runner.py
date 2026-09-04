from __future__ import annotations

import pandas as pd

from finplan.config.schema import ScenarioConfig
from finplan.engine.build import build_market, build_simulation
from finplan.engine.results import SimResults


def run(cfg: ScenarioConfig, mode: str = "det", seed: int | None = None,
        n_paths: int | None = None) -> SimResults:
    sim = build_simulation(cfg)
    years = sim.years()
    market = build_market(cfg, mode)
    if mode == "mc" and n_paths is not None:
        market.cfg.n_paths = n_paths
    paths = market.generate(len(years), seed=seed)
    rows = []
    for p in range(paths.n_paths):
        for led in sim.simulate_path(paths, p):
            row = led.to_row()
            row["path"] = p
            rows.append(row)
    ledger = pd.DataFrame(rows)
    return SimResults(ledger=ledger, mode=mode, seed=seed, path_labels=paths.labels)
