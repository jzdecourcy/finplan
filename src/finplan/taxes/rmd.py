"""Required minimum distributions (Pub 590-B, Uniform Lifetime Table).

SECURE 2.0 start ages: 73 for those born 1951-1959, 75 for those born 1960 or later.
(Born 1950 or earlier already started under older rules.)"""

from __future__ import annotations


def rmd_start_age(birth_year: int) -> int:
    if birth_year <= 1950:
        return 72
    if birth_year <= 1959:
        return 73
    return 75


def rmd_amount(prior_eoy_balance: float, age: int, table: dict[int, float]) -> float:
    if prior_eoy_balance <= 0:
        return 0.0
    factor = table.get(age) or table[max(table)]
    return prior_eoy_balance / factor
