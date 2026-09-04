"""PIA recompute golden tests against SSA's published worked example.

Sources (accessed 2026-09-04, cited in finplan/data/ss/awi_series.yaml):
- ssa.gov/oact/cola/bendpoints.html — published bend-point table
- ssa.gov/oact/ProgData/retirebenefit1.html and .../retirebenefit2.html —
  "Benefit Calculation Examples for Workers Retiring in 2026", Case A:
  born 1964, covered earnings 1986-2025 below, AIME $5,825, PIA $2,609.80,
  age-62 benefit $1,826 (30% reduction, rounded down to the dollar).
"""

import pytest

from finplan.config.schema import ScenarioConfig
from finplan.engine.build import build_simulation, derived_pias
from finplan.engine.simulator import ss_claim_factor
from finplan.ss.pia import bend_points, compute_aime, compute_pia_monthly

CASE_A_EARNINGS = {
    1986: 16196, 1987: 17283, 1988: 18191, 1989: 18971, 1990: 19909,
    1991: 20715, 1992: 21850, 1993: 22107, 1994: 22770, 1995: 23755,
    1996: 24994, 1997: 26533, 1998: 28007, 1999: 29657, 2000: 31392,
    2001: 32238, 2002: 32660, 2003: 33558, 2004: 35224, 2005: 36621,
    2006: 38419, 2007: 40281, 2008: 41330, 2009: 40826, 2010: 41914,
    2011: 43354, 2012: 44839, 2013: 45544, 2014: 47298, 2015: 49085,
    2016: 49783, 2017: 51651, 2018: 53677, 2019: 55848, 2020: 57590,
    2021: 62889, 2022: 66421, 2023: 69560, 2024: 73133, 2025: 75868,
}
CASE_A_BIRTH_YEAR = 1964


def test_bend_points_match_published_table():
    assert bend_points(1979) == (180, 1085)
    assert bend_points(2000) == (531, 3202)
    assert bend_points(2021) == (996, 6002)
    assert bend_points(2026) == (1286, 7749)


def test_bend_points_future_year_holds_latest():
    # Zero-future-wage-growth (today's dollars) convention: eligibility years beyond
    # the published AWI reuse the latest derivable bend points.
    assert bend_points(2039) == bend_points(2026)


def test_case_a_aime():
    assert compute_aime(CASE_A_EARNINGS, CASE_A_BIRTH_YEAR) == 5825


def test_case_a_pia():
    assert compute_pia_monthly(CASE_A_EARNINGS, CASE_A_BIRTH_YEAR) == 2609.80


def test_case_a_age62_benefit():
    benefit = compute_pia_monthly(CASE_A_EARNINGS, CASE_A_BIRTH_YEAR) * ss_claim_factor(62)
    assert int(benefit) == 1826  # SSA rounds down to the dollar


def test_fewer_than_35_years_pads_with_zeros():
    ten_years = {y: 50_000 for y in range(2016, 2026)}
    full = {y: 50_000 for y in range(1991, 2026)}
    assert compute_aime(ten_years, 1964) < compute_aime(full, 1964)


def _scenario(retirement_age: int) -> ScenarioConfig:
    return ScenarioConfig.model_validate({
        "sim": {"start_year": 2026, "horizon": "death"},
        "household": {
            "filing_status": "single",
            "people": [{
                "name": "sam", "birth_year": 1977, "retirement_age": retirement_age,
                "ss_claim_age": 67, "ss_pia_monthly": 9999,  # should be overridden
                "ss_earnings_history": {y: 60_000 + 1_000 * (y - 2000)
                                        for y in range(2000, 2026)},
                "life_expectancy_age": 90,
            }],
        },
        "accounts": [{"id": "cash", "type": "cash", "balance": 1_000_000}],
        "income": [{"id": "salary", "owner": "sam", "annual": 90_000,
                    "start": 2026, "end": "retirement"}],
        "expenses": [{"id": "living", "annual": 40_000, "start": 2026, "end": "death"}],
        "policies": {"withdrawal": {"order": ["cash"]}},
        "taxes": {"regime": "flat_stub", "flat_effective_rate": 0.20},
    })


def test_engine_overrides_entered_pia_and_early_retirement_lowers_it():
    pia_65 = derived_pias(_scenario(65))["sam"]
    pia_55 = derived_pias(_scenario(55))["sam"]
    assert 0 < pia_55 < pia_65  # zero years replace salary years in the top 35
    sim = build_simulation(_scenario(65))
    assert sim.household.person("sam").ss_pia_monthly == pia_65  # 9999 overridden


def test_wage_base_caps_projected_earnings():
    cfg = _scenario(65).model_copy(deep=True)
    cfg.income[0].annual = 1_000_000
    cfg.taxes.regime = "us_federal"
    cfg.taxes.state = "none"
    capped = derived_pias(cfg)["sam"]
    cfg.income[0].annual = 184_500  # 2026 SS wage base (us_federal_2026.yaml)
    at_base = derived_pias(cfg)["sam"]
    assert capped == at_base


def test_history_recompute_rejected_for_people_already_eligible():
    with pytest.raises(ValueError, match="under 62"):
        ScenarioConfig.model_validate({
            "sim": {"start_year": 2026, "horizon": 2030},
            "household": {
                "filing_status": "single",
                "people": [{"name": "old", "birth_year": 1960,
                            "ss_earnings_history": {2000: 50_000}}],
            },
            "accounts": [{"id": "cash", "type": "cash", "balance": 100}],
            "policies": {"withdrawal": {"order": ["cash"]}},
            "taxes": {"regime": "flat_stub", "flat_effective_rate": 0.20},
        })
