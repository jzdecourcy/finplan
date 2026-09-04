from __future__ import annotations

import numpy as np

from finplan.config.schema import DeterministicMarketCfg
from finplan.markets.base import ReturnPaths


class DeterministicMarket:
    """Single path of fixed real returns + fixed inflation, expressed nominally."""

    def __init__(self, cfg: DeterministicMarketCfg):
        self.cfg = cfg

    def generate(self, n_years: int, seed: int | None = None) -> ReturnPaths:
        assets = sorted(self.cfg.real_returns)
        infl = self.cfg.inflation
        nominal = np.array(
            [(1.0 + self.cfg.real_returns[a]) * (1.0 + infl) - 1.0 for a in assets]
        )
        returns = np.tile(nominal, (1, n_years, 1)).reshape(1, n_years, len(assets))
        inflation = np.full((1, n_years), infl)
        return ReturnPaths(assets=assets, returns=returns, inflation=inflation)
