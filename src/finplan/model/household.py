from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class FilingStatus(StrEnum):
    SINGLE = "single"
    MFJ = "mfj"


@dataclass
class Person:
    name: str
    birth_year: int
    retirement_age: int | None = None
    ss_claim_age: int | None = None
    ss_pia_monthly: float | None = None   # primary insurance amount at FRA, today's dollars
    life_expectancy_age: int = 95

    def age_in(self, year: int) -> int:
        return year - self.birth_year

    @property
    def retirement_year(self) -> int | None:
        return None if self.retirement_age is None else self.birth_year + self.retirement_age


@dataclass
class Household:
    people: list[Person]
    filing_status: FilingStatus
    state: str | None = None

    def person(self, name: str) -> Person:
        for p in self.people:
            if p.name == name:
                return p
        raise KeyError(f"no person named {name!r}")

    @property
    def horizon_year(self) -> int:
        return max(p.birth_year + p.life_expectancy_age for p in self.people)
