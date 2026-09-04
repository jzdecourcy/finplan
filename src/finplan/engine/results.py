from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass
class SimResults:
    ledger: pd.DataFrame          # tidy: one row per (path, year)
    mode: str
    seed: int | None = None
    path_labels: list[str] | None = None

    @property
    def n_paths(self) -> int:
        return self.ledger["path"].nunique()

    @property
    def success_probability(self) -> float:
        failed_paths = self.ledger.groupby("path")["failed"].any()
        return float(1.0 - failed_paths.mean())

    @property
    def terminal_wealth(self) -> pd.Series:
        last_year = self.ledger["year"].max()
        return self.ledger.loc[self.ledger["year"] == last_year].set_index("path")[
            "net_worth_real"
        ]

    def first_failure_years(self) -> pd.Series:
        failed = self.ledger[self.ledger["failed"]]
        return failed.groupby("path")["year"].min()

    def percentiles(self, column: str = "net_worth_real", pcts=(10, 25, 50, 75, 90)) -> pd.DataFrame:
        return (
            self.ledger.groupby("year")[column]
            .quantile([p / 100 for p in pcts])
            .unstack()
            .rename(columns={p / 100: f"p{p}" for p in pcts})
        )

    def metrics(self) -> dict:
        tw = self.terminal_wealth
        lifetime_tax = float(self.ledger.groupby("path")["tax_total"].sum().median())
        ffy = self.first_failure_years()
        return {
            "mode": self.mode,
            "seed": self.seed,
            "n_paths": int(self.n_paths),
            "success_probability": round(self.success_probability, 4),
            "terminal_wealth_real_median": round(float(np.median(tw)), 0),
            "terminal_wealth_real_p10": round(float(np.percentile(tw, 10)), 0),
            "median_lifetime_tax": round(lifetime_tax, 0),
            "median_first_failure_year": None if ffy.empty else int(ffy.median()),
        }
