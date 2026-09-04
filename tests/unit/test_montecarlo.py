import numpy as np
import pytest

from finplan.config.schema import MCAssetCfg, MonteCarloMarketCfg
from finplan.markets.montecarlo import MonteCarloMarket

CFG = MonteCarloMarketCfg(
    n_paths=50_000,
    assets={
        "stocks": MCAssetCfg(real_mean=0.05, vol=0.17),
        "bonds": MCAssetCfg(real_mean=0.015, vol=0.06),
    },
    inflation_mean=0.025,
    inflation_vol=0.015,
    correlation={"stocks_bonds": -0.10, "stocks_inflation": -0.20},
)


@pytest.fixture(scope="module")
def paths():
    return MonteCarloMarket(CFG).generate(n_years=10, seed=42)


def test_shapes(paths):
    assert paths.returns.shape == (50_000, 10, 2)
    assert paths.inflation.shape == (50_000, 10)
    assert paths.assets == ["bonds", "stocks"]


def test_sample_moments_match_config(paths):
    stocks = paths.returns[:, :, 1]
    infl = paths.inflation
    real_stocks = (1 + stocks) / (1 + infl) - 1
    assert real_stocks.mean() == pytest.approx(0.05, abs=0.005)
    assert real_stocks.std() == pytest.approx(0.17, abs=0.01)
    assert infl.mean() == pytest.approx(0.025, abs=0.001)
    assert infl.std() == pytest.approx(0.015, abs=0.001)


def test_correlations_match_config(paths):
    bonds_real = np.log1p((1 + paths.returns[:, :, 0]) / (1 + paths.inflation) - 1).ravel()
    stocks_real = np.log1p((1 + paths.returns[:, :, 1]) / (1 + paths.inflation) - 1).ravel()
    infl = paths.inflation.ravel()
    assert np.corrcoef(stocks_real, bonds_real)[0, 1] == pytest.approx(-0.10, abs=0.02)
    assert np.corrcoef(stocks_real, infl)[0, 1] == pytest.approx(-0.20, abs=0.02)


def test_seed_reproducibility():
    market = MonteCarloMarket(
        MonteCarloMarketCfg(n_paths=100, assets=CFG.assets, correlation=CFG.correlation)
    )
    a = market.generate(5, seed=7)
    b = market.generate(5, seed=7)
    c = market.generate(5, seed=8)
    assert np.array_equal(a.returns, b.returns)
    assert not np.array_equal(a.returns, c.returns)


def test_no_sub_negative_100_returns(paths):
    assert (paths.returns > -1.0).all()


def test_bad_correlation_matrix_rejected():
    cfg = MonteCarloMarketCfg(
        n_paths=10,
        assets=CFG.assets,
        correlation={"stocks_bonds": 0.99, "stocks_inflation": 0.99,
                     "bonds_inflation": -0.99},
    )
    with pytest.raises(ValueError, match="positive semi-definite"):
        MonteCarloMarket(cfg).generate(5, seed=1)
