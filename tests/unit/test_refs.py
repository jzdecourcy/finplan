import pytest

from finplan.model.refs import RefContext, resolve

CTX = RefContext(
    birth_years={"sam": 1985, "alex": 1987},
    retirement_years={"sam": 2040, "alex": 2049},
    horizon_year=2082,
)


def test_absolute_year():
    assert resolve(2030, CTX) == 2030


def test_death():
    assert resolve("death", CTX) == 2082


def test_retirement_owner_specific():
    ctx = RefContext(CTX.birth_years, CTX.retirement_years, CTX.horizon_year, owner="sam")
    assert resolve("retirement", ctx) == 2040


def test_retirement_household_level_uses_latest():
    assert resolve("retirement", CTX) == 2049


def test_age_ref():
    assert resolve("age:sam:65", CTX) == 2050


def test_bad_refs():
    with pytest.raises(ValueError):
        resolve("age:nobody:65", CTX)
    with pytest.raises(ValueError):
        resolve("whenever", CTX)
