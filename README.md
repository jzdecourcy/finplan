# finplan

A personal financial planning and scenario-modeling environment. A deterministic /
Monte Carlo / historical-backtest cash-flow engine with detailed US federal + Michigan
tax modeling, driven by composable YAML scenarios — operated conversationally through
Claude Code (see `CLAUDE.md`; the human never edits YAML by hand).

## Getting started

1. Clone this repo into a **private** repository of your own — your plan structure and
   accumulated `knowledge/` will contain personal detail (names, salaries; never balances,
   which stay gitignored in `snapshots/`).
2. `python -m pip install -e .[dev]` and `pytest` to confirm the engine works.
3. Open the repo in Claude Code and run **`/interview`** — a phased, resumable onboarding
   interview that builds your `scenarios/base.yaml` and first snapshot conversationally.
   A fictional worked example lives in `scenarios/examples/`:
   `plan run -f scenarios/examples/base.yaml -f scenarios/examples/retire_at_55.yaml`

## How it fits together

- **Scenarios compose**: `scenarios/base.yaml` + small overlays
  (`scenarios/overlays/retire_at_55.yaml`, ...) merged by `id`, so what-ifs stay small,
  diffable, and mixable: `plan run -f scenarios/base.yaml -f scenarios/overlays/retire_at_55.yaml`
- **Balances live in snapshots** (`snapshots/YYYY-MM-DD.yaml`, gitignored), refreshed via
  `plan update` (or by telling Claude, or dropping brokerage CSV exports in `inbox/`).
  The plan structure never changes for a balance update.
- **Taxes are computed, never estimated**: bracket walks, LTCG stacking, Social Security
  provisional income, RMDs, FICA, NIIT, Michigan flat tax with retirement subtraction and
  MESP 529 deduction. Parameters live in per-year data files
  (`src/finplan/data/tax/*.yaml`) with cited primary sources, golden-tested against IRS
  worksheet examples (`tests/golden/`).
- **Agents advise, code computes**: `.claude/agents/` defines a tax-strategist, a
  retirement-planner, and a data-intake specialist; they read engine output and write
  their accumulated knowledge to `knowledge/` — never numbers of their own.

## Commands

```
plan run      -f scenarios/base.yaml [--mode det|mc|hist] [--seed N] [-o runs/name]
plan compare  -f scenarios/base.yaml --scenario "r55:-f scenarios/overlays/retire_at_55.yaml"
plan validate / plan show-config [--diff-base]
plan update [brokerage=462000 ...] / plan status
plan tax-year --year 2026 --filing mfj --income wages=180000 --income ltcg=20000
plan tax-year --year 2026 --filing mfj --income trad=80000 --income aca_premium=24000 --income aca_hh=2
```

## Known limits (v1)

Federal + Michigan only; simplified AMT-free world; standard
deduction only; average-cost basis; no loss carryforwards; annual steps. The full,
dated list lives in `knowledge/assumptions.md`. This is a planning tool, not tax advice —
consequential moves go through a human CPA (`knowledge/open-questions.md`).

## Development

```
python -m pip install -e .[dev]
pytest
```
