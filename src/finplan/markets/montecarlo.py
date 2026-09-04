"""Correlated Monte Carlo market model.

Asset real returns are lognormal (no path can lose more than 100%); inflation is normal.
Cross-correlations (asset-asset and asset-inflation) come from the config's pairwise
`correlation` map; unspecified pairs default to 0. Nominal return = (1+real)(1+inflation)-1.
"""

from __future__ import annotations

import numpy as np

from finplan.config.schema import MonteCarloMarketCfg
from finplan.markets.base import ReturnPaths


def _correlation_matrix(names: list[str], pairs: dict[str, float]) -> np.ndarray:
    n = len(names)
    corr = np.eye(n)
    idx = {name: i for i, name in enumerate(names)}
    for key, rho in pairs.items():
        a, _, b = key.partition("_")
        if a not in idx or b not in idx:
            raise ValueError(f"correlation key {key!r}: unknown series (use e.g. stocks_bonds)")
        corr[idx[a], idx[b]] = corr[idx[b], idx[a]] = rho
    # validate positive semi-definite early, with a clear message
    eigenvalues = np.linalg.eigvalsh(corr)
    if eigenvalues.min() < -1e-8:
        raise ValueError("correlation matrix is not positive semi-definite")
    return corr


class MonteCarloMarket:
    def __init__(self, cfg: MonteCarloMarketCfg):
        self.cfg = cfg

    def generate(self, n_years: int, seed: int | None = None) -> ReturnPaths:
        cfg = self.cfg
        assets = sorted(cfg.assets)
        series = assets + ["inflation"]
        corr = _correlation_matrix(series, cfg.correlation)
        chol = np.linalg.cholesky(corr + 1e-12 * np.eye(len(series)))
        rng = np.random.default_rng(seed)
        z = rng.standard_normal((cfg.n_paths, n_years, len(series))) @ chol.T

        real = np.empty((cfg.n_paths, n_years, len(assets)))
        for i, name in enumerate(assets):
            a = cfg.assets[name]
            sigma = a.vol / (1.0 + a.real_mean)          # log-space vol approximation
            mu = np.log1p(a.real_mean) - 0.5 * sigma**2  # so E[return] ~= real_mean
            real[:, :, i] = np.expm1(mu + sigma * z[:, :, i])
        inflation = cfg.inflation_mean + cfg.inflation_vol * z[:, :, -1]
        nominal = (1.0 + real) * (1.0 + inflation[:, :, None]) - 1.0
        return ReturnPaths(assets=assets, returns=nominal, inflation=inflation)
