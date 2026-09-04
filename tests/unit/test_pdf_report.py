"""PDF report generation: renders without error for det and MC runs and lands
alongside the other run artifacts."""

import pytest

from finplan.config.schema import ScenarioConfig
from finplan.engine.runner import run
from finplan.report.pdf import write_pdf_report

CONFIG = {
    "sim": {"start_year": 2030, "horizon": 2040},
    "household": {
        "filing_status": "single",
        "people": [{"name": "sam", "birth_year": 1975, "retirement_age": 60,
                    "ss_claim_age": 67, "ss_pia_monthly": 2500,
                    "life_expectancy_age": 90}],
    },
    "accounts": [
        {"id": "cash", "type": "cash", "balance": 100_000},
        {"id": "brokerage", "type": "taxable", "balance": 400_000},
        {"id": "ira", "type": "traditional", "owner": "sam", "balance": 600_000},
        {"id": "roth", "type": "roth", "owner": "sam", "balance": 100_000},
    ],
    "income": [{"id": "salary", "owner": "sam", "annual": 120_000,
                "start": 2030, "end": "retirement"}],
    "expenses": [{"id": "living", "annual": 70_000, "start": 2030, "end": "death"}],
    "taxes": {"regime": "flat_stub", "flat_effective_rate": 0.20},
}


@pytest.mark.parametrize("mode,n_paths", [("det", None), ("mc", 25)])
def test_pdf_report_renders(tmp_path, mode, n_paths):
    cfg = ScenarioConfig.model_validate(CONFIG)
    results = run(cfg, mode=mode, seed=7, n_paths=n_paths)
    out = write_pdf_report(results, cfg, tmp_path / "report.pdf")
    data = out.read_bytes()
    assert data[:5] == b"%PDF-"
    assert len(data) > 20_000                      # all six pages rendered
    assert data.count(b"/Type /Page ") == 6


def test_pdf_written_by_run_scenario(tmp_path):
    import yaml

    from finplan.api import run_scenario

    cfg_file = tmp_path / "scenario.yaml"
    cfg_file.write_text(yaml.safe_dump(CONFIG), encoding="utf-8")
    run_scenario([cfg_file], mode="det", out_dir=tmp_path / "out")
    assert (tmp_path / "out" / "report.pdf").exists()
