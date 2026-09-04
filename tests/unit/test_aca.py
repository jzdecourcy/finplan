"""ACA § 36B pure-math tests against the published 2026 parameters.

FPL values: 2025 HHS guidelines (govern the 2026 coverage year), 90 FR 5917.
Percentages: Rev. Proc. 2025-25 § 3.01.
"""

import pytest

from finplan.taxes.aca import (
    aca_magi,
    applicable_percentage,
    federal_poverty_line,
    premium_tax_credit,
)
from finplan.taxes.params import load_federal

ACA = load_federal(2026)["aca"]


class TestFederalPovertyLine:
    @pytest.mark.parametrize(
        "size,expected",
        [(1, 15650), (2, 21150), (3, 26650), (4, 32150), (5, 37650), (8, 54150)],
    )
    def test_matches_published_2025_guidelines(self, size, expected):
        assert federal_poverty_line(size, ACA) == expected


class TestApplicablePercentage:
    def test_flat_below_133(self):
        assert applicable_percentage(0.50, ACA) == pytest.approx(0.0210)
        assert applicable_percentage(1.00, ACA) == pytest.approx(0.0210)
        assert applicable_percentage(1.3299, ACA) == pytest.approx(0.0210)

    def test_statutory_jump_at_133(self):
        # discontinuity is real: 2.10 just below, 3.14 at exactly 133%
        assert applicable_percentage(1.33, ACA) == pytest.approx(0.0314)

    @pytest.mark.parametrize("boundary,pct", [(1.50, 0.0419), (2.00, 0.0660),
                                              (2.50, 0.0844), (3.00, 0.0996)])
    def test_continuity_at_interior_boundaries(self, boundary, pct):
        # bands meet: approaching from below equals the boundary's own band value
        assert applicable_percentage(boundary - 1e-9, ACA) == pytest.approx(pct, abs=1e-6)
        assert applicable_percentage(boundary, ACA) == pytest.approx(pct)

    def test_midband_interpolation_225(self):
        # 225% is halfway through the 200-250 band: 6.60 + 0.5*(8.44-6.60) = 7.52
        assert applicable_percentage(2.25, ACA) == pytest.approx(0.0752)

    def test_flat_top_band(self):
        assert applicable_percentage(3.50, ACA) == pytest.approx(0.0996)
        assert applicable_percentage(4.00, ACA) == pytest.approx(0.0996)

    def test_cliff(self):
        # exactly 400% is still eligible ("does not exceed"); above is not
        assert applicable_percentage(4.00, ACA) is not None
        assert applicable_percentage(4.0001, ACA) is None


class TestAcaMagi:
    def test_addbacks(self):
        # AGI + tax-exempt interest + untaxed SS
        assert aca_magi(24000, 5000, 30000, 4000) == 55000

    def test_no_ss(self):
        assert aca_magi(50000, 0, 0, 0) == 50000


class TestPremiumTaxCredit:
    def test_midband_case(self):
        # MAGI 47,587.50 = 225% of FPL(2)=21,150; contribution 7.52% = 3,578.58
        r = premium_tax_credit(47587.50, 2, 24000, ACA)
        assert r.fpl == 21150
        assert r.fpl_pct == pytest.approx(2.25)
        assert r.applicable_pct == pytest.approx(0.0752)
        assert r.expected_contribution == pytest.approx(3578.58)
        assert r.credit == pytest.approx(20421.42)

    def test_cliff_pair(self):
        under = premium_tax_credit(84500, 2, 24000, ACA)   # 399.5% FPL
        over = premium_tax_credit(84700, 2, 24000, ACA)    # 400.5% FPL
        assert under.credit == pytest.approx(24000 - 0.0996 * 84500)  # 15,583.80
        assert over.credit == 0.0
        assert over.applicable_pct == 0.0

    def test_below_133(self):
        r = premium_tax_credit(25000, 2, 24000, ACA)       # 118.2% FPL
        assert r.credit == pytest.approx(24000 - 0.0210 * 25000)      # 23,475
        assert r.fpl_pct < 1.33

    def test_credit_floors_at_zero(self):
        # tiny benchmark: contribution exceeds it -> no negative credit
        r = premium_tax_credit(84000, 2, 5000, ACA)
        assert r.credit == 0.0
        assert r.expected_contribution > 5000
