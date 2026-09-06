"""Features added after the 2026-09-06 interview replay test: dated contribution
windows, beneficiary-aware 529 draws, per-earner + QBI `plan tax-year`, and the
calibrated Monte Carlo defaults."""

import pytest
from click.testing import CliRunner

from finplan.cli.main import cli
from finplan.config.schema import MonteCarloMarketCfg, ScenarioConfig
from finplan.engine.runner import run


def _base(**over):
    cfg = {
        "sim": {"start_year": 2026, "horizon": 2029},
        "household": {
            "filing_status": "mfj",
            "people": [
                {"name": "a", "birth_year": 1977, "retirement_age": 65,
                 "ss_pia_monthly": 3000, "life_expectancy_age": 95},
                {"name": "b", "birth_year": 1975, "retirement_age": 65,
                 "ss_pia_monthly": 3000, "life_expectancy_age": 95},
            ],
        },
        "accounts": [
            {"id": "cash", "type": "cash", "balance": 500_000},
            {"id": "401k-a", "type": "traditional", "owner": "a", "balance": 0,
             "allocation": {"stocks": 1.0}},
            {"id": "roth401k-a", "type": "roth", "owner": "a", "balance": 0,
             "allocation": {"stocks": 1.0}},
            {"id": "529-kid1", "type": "529", "owner": "a", "beneficiary": "kid1",
             "balance": 30_000, "cost_basis": 30_000, "allocation": {"cash": 1.0}},
            {"id": "529-kid2", "type": "529", "owner": "a", "beneficiary": "kid2",
             "balance": 30_000, "cost_basis": 30_000, "allocation": {"cash": 1.0}},
        ],
        "income": [
            {"id": "sal-a", "owner": "a", "kind": "salary", "annual": 100_000,
             "start": 2026, "end": "retirement"},
        ],
        "expenses": [{"id": "living", "annual": 50_000, "start": 2026, "end": "death"}],
        "policies": {"withdrawal": {"order": ["cash", "taxable", "traditional", "roth", "hsa"]},
                     "contribution": {"pretax": [], "posttax": [], "priority": ["cash"]}},
        "market": {"deterministic": {"real_returns": {"stocks": 0.0, "bonds": 0.0, "cash": 0.0},
                                     "inflation": 0.0}},
        "taxes": {"regime": "us_federal", "state": "michigan", "base_params_year": 2026},
    }
    cfg.update(over)
    return ScenarioConfig.model_validate(cfg)


def test_contribution_window_switches_policy_by_year():
    cfg = _base(policies={
        "withdrawal": {"order": ["cash", "taxable", "traditional", "roth", "hsa"]},
        "contribution": {
            "pretax": [
                {"account": "401k-a", "amount": 10_000, "end": 2026},
                {"account": "401k-a", "amount": 20_000, "start": 2027},
            ],
            "posttax": [{"account": "roth401k-a", "amount": 5_000, "end": 2026}],
            "priority": ["cash"],
        },
    })
    led = run(cfg, mode="det").ledger.set_index("year")
    assert led.loc[2026, "bal_401k-a"] == pytest.approx(10_000)
    assert led.loc[2027, "bal_401k-a"] == pytest.approx(30_000)
    assert led.loc[2028, "bal_401k-a"] == pytest.approx(50_000)
    assert led.loc[2026, "bal_roth401k-a"] == pytest.approx(5_000)
    assert led.loc[2027, "bal_roth401k-a"] == pytest.approx(5_000)   # window closed


def test_contribution_window_retirement_ref_resolves_per_owner():
    # owner a retires 2028 (age 51); a "start: retirement" pretax item never fires
    # while wages exist, and the undated one runs to retirement
    cfg = _base(
        household={"filing_status": "mfj", "people": [
            {"name": "a", "birth_year": 1977, "retirement_age": 51,
             "ss_pia_monthly": 3000, "life_expectancy_age": 95},
            {"name": "b", "birth_year": 1975, "retirement_age": 65,
             "ss_pia_monthly": 3000, "life_expectancy_age": 95}]},
        policies={
            "withdrawal": {"order": ["cash", "taxable", "traditional", "roth", "hsa"]},
            "contribution": {
                "pretax": [{"account": "401k-a", "amount": 10_000, "end": 2027}],
                "priority": ["cash"]},
        },
    )
    led = run(cfg, mode="det").ledger.set_index("year")
    assert led.loc[2027, "bal_401k-a"] == pytest.approx(20_000)
    assert led.loc[2029, "bal_401k-a"] == pytest.approx(20_000)


def test_529_draws_prefer_named_beneficiary_then_fall_back():
    cfg = _base(expenses=[
        {"id": "living", "annual": 50_000, "start": 2026, "end": "death"},
        {"id": "college-kid2", "annual": 20_000, "start": 2026, "end": 2027,
         "education": True, "beneficiary": "kid2"},
    ])
    led = run(cfg, mode="det").ledger.set_index("year")
    # kid2's plan is drained first even though kid1's account is listed first
    assert led.loc[2026, "bal_529-kid2"] == pytest.approx(10_000)
    assert led.loc[2026, "bal_529-kid1"] == pytest.approx(30_000)
    # year 2: kid2's remaining 10k, then 10k of sibling transfer from kid1's plan
    assert led.loc[2027, "bal_529-kid2"] == pytest.approx(0)
    assert led.loc[2027, "bal_529-kid1"] == pytest.approx(20_000)


def test_529_draws_without_beneficiary_keep_config_order():
    cfg = _base(expenses=[
        {"id": "living", "annual": 50_000, "start": 2026, "end": "death"},
        {"id": "college", "annual": 20_000, "start": 2026, "end": 2026, "education": True},
    ])
    led = run(cfg, mode="det").ledger.set_index("year")
    assert led.loc[2026, "bal_529-kid1"] == pytest.approx(10_000)
    assert led.loc[2026, "bal_529-kid2"] == pytest.approx(30_000)


def test_tax_year_per_earner_wages_and_qbi():
    runner = CliRunner()
    base = ["tax-year", "--year", "2026", "--filing", "mfj", "--age", "49", "--age", "51"]
    single = runner.invoke(cli, base + ["--income", "wages=200000", "--income", "business=250000"])
    split = runner.invoke(cli, base + ["--wages", "a=100000", "--wages", "b=100000",
                                       "--income", "business=250000"])
    qbi = runner.invoke(cli, base + ["--wages", "a=100000", "--wages", "b=100000",
                                     "--income", "business=250000", "--qbi-wage-cap", "250000"])
    for r in (single, split, qbi):
        assert r.exit_code == 0, r.output

    def row(out, label):
        line = next(l for l in out.splitlines() if l.strip().startswith(label))
        return float(line.split("$")[1].replace(",", ""))

    # same total wages, but two earners each under the SS wage base pay more OASDI
    assert row(split.output, "FICA") > row(single.output, "FICA")
    assert row(qbi.output, "QBI deduction") == pytest.approx(50_000, rel=0.01)
    assert row(qbi.output, "federal income tax") < row(split.output, "federal income tax")
    both = runner.invoke(cli, base + ["--wages", "a=1", "--income", "wages=1"])
    assert both.exit_code != 0


def test_monte_carlo_defaults_are_calibrated():
    mc = MonteCarloMarketCfg()
    assert mc.n_paths == 2000
    assert mc.correlation == {"stocks_bonds": -0.10, "stocks_inflation": -0.20,
                              "bonds_inflation": -0.40}
    assert MonteCarloMarketCfg(correlation={}).correlation == {}
