from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import numpy as np


@dataclass
class ReturnPaths:
    """Pre-generated market paths.

    returns: nominal returns, shape [n_paths, n_years, n_assets] in `assets` order
    inflation: shape [n_paths, n_years]
    """

    assets: list[str]
    returns: np.ndarray
    inflation: np.ndarray
    labels: list[str] | None = None      # per-path label (e.g. historical start year)

    @property
    def n_paths(self) -> int:
        return self.returns.shape[0]

    @property
    def n_years(self) -> int:
        return self.returns.shape[1]

    def year_returns(self, path: int, year_idx: int) -> dict[str, float]:
        return {a: float(self.returns[path, year_idx, i]) for i, a in enumerate(self.assets)}


class MarketModel(Protocol):
    def generate(self, n_years: int, seed: int | None = None) -> ReturnPaths: ...
