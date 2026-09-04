"""YearRef: symbolic year references used throughout scenario configs.

Accepted forms:
    2028                      absolute calendar year
    "retirement"              the (single) owner's retirement year; for household-level
                              streams, the LATEST retirement year in the household
    "death"                   end of simulation horizon
    "age:<person>:<n>"        the year <person> turns <n>
"""

from __future__ import annotations

from dataclasses import dataclass

YearRef = int | str


@dataclass(frozen=True)
class RefContext:
    """Everything needed to resolve a YearRef to a calendar year."""

    birth_years: dict[str, int]          # person name -> birth year
    retirement_years: dict[str, int]     # person name -> calendar year of retirement
    horizon_year: int                    # last simulated year ("death")
    owner: str | None = None             # stream owner, if any


def resolve(ref: YearRef, ctx: RefContext) -> int:
    if isinstance(ref, int):
        return ref
    if ref == "death":
        return ctx.horizon_year
    if ref == "retirement":
        if ctx.owner is not None:
            try:
                return ctx.retirement_years[ctx.owner]
            except KeyError:
                raise ValueError(f"person {ctx.owner!r} has no retirement_age set") from None
        if not ctx.retirement_years:
            raise ValueError("'retirement' ref used but nobody has a retirement_age")
        return max(ctx.retirement_years.values())
    if ref.startswith("age:"):
        try:
            _, person, age = ref.split(":")
            return ctx.birth_years[person] + int(age)
        except (ValueError, KeyError):
            raise ValueError(f"bad age ref {ref!r}; expected 'age:<person>:<years>'") from None
    raise ValueError(f"unrecognized year reference {ref!r}")
