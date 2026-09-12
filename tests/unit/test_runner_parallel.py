"""Path-parallel MC runs must be bit-identical to the serial loop, and the auto
worker heuristic must stay at 1 for det/small/nested runs."""

import multiprocessing
from unittest import mock

from finplan.config.schema import ScenarioConfig
from finplan.engine.runner import default_workers, run

CONFIG = {
    "sim": {"start_year": 2030, "horizon": 2036},
    "household": {
        "filing_status": "single",
        "people": [{"name": "sam", "birth_year": 1980, "life_expectancy_age": 90}],
    },
    "accounts": [
        {"id": "cash", "type": "cash", "balance": 50_000},
        {"id": "brokerage", "type": "taxable", "balance": 200_000, "cost_basis": 150_000},
    ],
    "income": [{"id": "salary", "owner": "sam", "annual": 80_000, "start": 2030, "end": 2031}],
    "expenses": [{"id": "living", "annual": 50_000, "start": 2030, "end": 2036}],
    "policies": {"withdrawal": {"order": ["cash", "taxable"]}},
    "market": {"monte_carlo": {"n_paths": 40}},
    "taxes": {"regime": "flat_stub", "flat_effective_rate": 0.20},
}


def test_parallel_matches_serial():
    cfg = ScenarioConfig.model_validate(CONFIG)
    serial = run(cfg, mode="mc", seed=11, workers=1)
    parallel = run(cfg, mode="mc", seed=11, workers=3)
    assert parallel.n_paths == 40 and parallel.seed == 11
    assert serial.ledger.equals(parallel.ledger)


def test_unseeded_parallel_pins_a_seed_and_is_reproducible():
    cfg = ScenarioConfig.model_validate(CONFIG)
    first = run(cfg, mode="mc", seed=None, workers=2)
    assert first.seed is not None
    again = run(cfg, mode="mc", seed=first.seed, workers=1)
    assert first.ledger.equals(again.ledger)


def test_workers_capped_at_path_count():
    cfg = ScenarioConfig.model_validate(CONFIG)
    res = run(cfg, mode="mc", seed=1, n_paths=3, workers=8)
    assert res.n_paths == 3 and sorted(res.ledger["path"].unique()) == [0, 1, 2]


def test_default_workers_heuristic():
    assert default_workers("det", 1) == 1
    assert default_workers("hist", 100) == 1
    assert default_workers("mc", 199) == 1
    with mock.patch("os.cpu_count", return_value=8):
        assert default_workers("mc", 2000) == 6
        assert default_workers("mc", 4) == 1          # below the min-paths threshold
    with mock.patch("os.cpu_count", return_value=64):
        assert default_workers("mc", 2000) == 16      # auto cap
    with mock.patch.object(multiprocessing, "parent_process", return_value=object()):
        assert default_workers("mc", 2000) == 1       # never nest inside a worker
