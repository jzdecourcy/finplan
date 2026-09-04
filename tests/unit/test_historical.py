import numpy as np
import pytest

from finplan.config.schema import HistoricalMarketCfg
from finplan.markets.historical import HistoricalMarket, load_series


def test_series_loads_with_landmarks():
    df = load_series().set_index("year")
    assert df.loc[1931, "stocks"] == pytest.approx(-0.438, abs=0.01)
    assert df.loc[2008, "stocks"] == pytest.approx(-0.366, abs=0.01)
    assert df.loc[2022, "bonds"] == pytest.approx(-0.178, abs=0.01)
    assert df.loc[1980, "inflation"] == pytest.approx(0.125, abs=0.01)


def test_rolling_windows():
    paths = HistoricalMarket(HistoricalMarketCfg()).generate(n_years=30)
    df = load_series()
    assert paths.n_years == 30
    assert paths.n_paths == len(df) - 30 + 1
    assert paths.labels[0] == str(int(df["year"].min()))
    # window starting 1966: first year's stock return matches the source row
    idx_1966 = paths.labels.index("1966")
    src = df.set_index("year")
    assert paths.year_returns(idx_1966, 0)["stocks"] == pytest.approx(
        src.loc[1966, "stocks"]
    )


def test_horizon_longer_than_record_rejected():
    with pytest.raises(ValueError, match="exceeds"):
        HistoricalMarket(HistoricalMarketCfg()).generate(n_years=150)


def test_1966_cohort_sequence_risk():
    """The 1966 retiree is the classic SWR failure case: a 60/40 portfolio with a 6%
    initial real withdrawal depletes well inside 30 years, while the 1975 cohort survives
    the same rule comfortably."""
    paths = HistoricalMarket(HistoricalMarketCfg()).generate(n_years=30)

    def survives(start_label: str, withdrawal_rate: float) -> bool:
        p = paths.labels.index(start_label)
        balance = 1_000_000.0
        spend = withdrawal_rate * balance
        for y in range(30):
            r = paths.year_returns(p, y)
            balance -= spend
            if balance <= 0:
                return False
            balance *= 1 + 0.6 * r["stocks"] + 0.4 * r["bonds"]
            spend *= 1 + float(paths.inflation[p, y])
        return balance > 0

    assert not survives("1966", 0.06)
    assert survives("1975", 0.06)
    assert survives("1966", 0.03)
