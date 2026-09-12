from __future__ import annotations

import multiprocessing
import os
from concurrent.futures import ProcessPoolExecutor

import numpy as np
import pandas as pd

from finplan.config.schema import ScenarioConfig
from finplan.engine.build import build_market, build_simulation
from finplan.engine.results import SimResults

# Below this many paths the process-spawn cost (Python + numpy + pandas import per
# worker on Windows) outweighs the ~10 ms/path simulation work.
_PARALLEL_MIN_PATHS = 200
# Measured flat from 8 to 30 workers on a 32-core box; more just adds spawn cost.
_MAX_AUTO_WORKERS = 16


def _simulate_slice(cfg: ScenarioConfig, mode: str, seed: int | None,
                    n_paths: int | None, lo: int, hi: int) -> list[dict]:
    """Simulate paths [lo, hi) and return their ledger rows.

    Top-level so ProcessPoolExecutor can pickle it. The simulation object itself
    isn't picklable, so each worker rebuilds it from the (small) config and
    regenerates the full return array from the seed; both are ~20 ms.
    """
    sim = build_simulation(cfg)
    years = sim.years()
    market = build_market(cfg, mode)
    if mode == "mc" and n_paths is not None:
        market.cfg.n_paths = n_paths
    paths = market.generate(len(years), seed=seed)
    rows = []
    for p in range(lo, hi):
        for led in sim.simulate_path(paths, p):
            row = led.to_row()
            row["path"] = p
            rows.append(row)
    return rows


def default_workers(mode: str, n_paths: int) -> int:
    """Auto worker count: parallel only for MC runs big enough to amortise spawn,
    and never from inside another worker process (e.g. a sweep cell)."""
    if mode != "mc" or n_paths < _PARALLEL_MIN_PATHS:
        return 1
    if multiprocessing.parent_process() is not None:
        return 1
    return max(1, min(n_paths, _MAX_AUTO_WORKERS, (os.cpu_count() or 2) - 2))


def run(cfg: ScenarioConfig, mode: str = "det", seed: int | None = None,
        n_paths: int | None = None, workers: int | None = None) -> SimResults:
    # Generate once in the parent for labels/path count; cheap (numpy only).
    market = build_market(cfg, mode)
    if mode == "mc" and n_paths is not None:
        market.cfg.n_paths = n_paths
    n_years = len(build_simulation(cfg).years())
    if workers is None:
        workers = default_workers(mode, market.cfg.n_paths if mode == "mc" else 1)
    if workers > 1 and seed is None:
        # Workers regenerate the return array independently, so pin a seed now
        # to keep every slice on the same draw. Recorded in the results.
        seed = int(np.random.SeedSequence().generate_state(1)[0])
    paths = market.generate(n_years, seed=seed)
    total = paths.n_paths
    workers = max(1, min(workers, total))

    if workers <= 1:
        rows = _simulate_slice(cfg, mode, seed, n_paths, 0, total)
    else:
        bounds = np.linspace(0, total, workers + 1, dtype=int)
        with ProcessPoolExecutor(max_workers=workers) as pool:
            futures = [pool.submit(_simulate_slice, cfg, mode, seed, n_paths, int(lo), int(hi))
                       for lo, hi in zip(bounds[:-1], bounds[1:]) if hi > lo]
            rows = [r for f in futures for r in f.result()]   # submission order = path order
    ledger = pd.DataFrame(rows)
    return SimResults(ledger=ledger, mode=mode, seed=seed, path_labels=paths.labels)
