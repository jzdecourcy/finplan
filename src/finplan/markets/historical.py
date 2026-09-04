"""Historical backtest market model: rolling windows over the long-run annual US series.

Data file: finplan/data/market/historical_annual.csv with columns
    year, stocks, bonds, cash, inflation
holding NOMINAL total returns (and CPI inflation) per calendar year. One simulation path
per rolling start year; windows shorter than the horizon wrap the labels but are simply
not generated (only full windows run, so every path covers the whole plan).
"""

from __future__ import annotations

from importlib import resources

import numpy as np
import pandas as pd

from finplan.config.schema import HistoricalMarketCfg
from finplan.markets.base import ReturnPaths

_DATA_PKG = "finplan.data.market"
_FILE = "historical_annual.csv"


def load_series() -> pd.DataFrame:
    path = resources.files(_DATA_PKG) / _FILE
    with resources.as_file(path) as p:
        df = pd.read_csv(p)
    required = {"year", "stocks", "bonds", "cash", "inflation"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"{_FILE} missing columns: {sorted(missing)}")
    return df.sort_values("year").reset_index(drop=True)


class HistoricalMarket:
    def __init__(self, cfg: HistoricalMarketCfg):
        self.cfg = cfg

    def generate(self, n_years: int, seed: int | None = None) -> ReturnPaths:
        df = load_series()
        if len(df) < n_years:
            raise ValueError(
                f"horizon of {n_years} years exceeds the {len(df)}-year historical record; "
                "shorten the horizon or use Monte Carlo"
            )
        assets = ["bonds", "cash", "stocks"]
        n_windows = len(df) - n_years + 1
        returns = np.empty((n_windows, n_years, len(assets)))
        inflation = np.empty((n_windows, n_years))
        labels = []
        values = {a: df[a].to_numpy() for a in assets}
        infl = df["inflation"].to_numpy()
        for w in range(n_windows):
            for i, a in enumerate(assets):
                returns[w, :, i] = values[a][w : w + n_years]
            inflation[w] = infl[w : w + n_years]
            labels.append(str(int(df["year"].iloc[w])))
        return ReturnPaths(assets=assets, returns=returns, inflation=inflation, labels=labels)
