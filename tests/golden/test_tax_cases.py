"""Golden-file tax tests.

Each YAML in tax_cases/ is one case:
    name: pub915-example-1
    source: "IRS Pub 915 (2025), Example 1"
    params_year: 2026
    state: none | michigan
    input:            # TaxInput fields (filing_status as string; ages as name->age map)
      filing_status: mfj
      wages: 50000
      ...
    expected:         # any TaxResult fields; each asserted within tolerance
      taxable_ss: 2990
      federal: 12345
    tolerance: 1.0    # optional, dollars (default 1)
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from finplan.model.household import FilingStatus
from finplan.taxes.engine import compute_year_tax
from finplan.taxes.params import load_federal, load_michigan
from finplan.taxes.types import TaxInput

CASE_DIR = Path(__file__).parent / "tax_cases"
CASES = sorted(CASE_DIR.glob("*.yaml"))


def _load_case(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


@pytest.mark.parametrize("case_path", CASES, ids=lambda p: p.stem)
def test_golden_tax_case(case_path: Path):
    case = _load_case(case_path)
    raw = dict(case["input"])
    raw["filing_status"] = FilingStatus(raw["filing_status"])
    raw.setdefault("year", case["params_year"])
    inp = TaxInput(**raw)
    params = load_federal(case["params_year"])
    mi = load_michigan(case["params_year"]) if case.get("state") == "michigan" else None
    result = compute_year_tax(inp, params, mi)
    tol = case.get("tolerance", 1.0)
    for field_name, expected in case["expected"].items():
        actual = getattr(result, field_name)
        assert actual == pytest.approx(expected, abs=tol), (
            f"{case['name']}: {field_name} = {actual:,.2f}, expected {expected:,.2f} "
            f"(source: {case.get('source', 'n/a')})"
        )
