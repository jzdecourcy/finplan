# finplan

A personal financial planning engine you operate by talking to Claude Code.

finplan is three pieces that never share a directory:

| Piece | What it is | Where it lives |
|---|---|---|
| **Engine** | A Python package with a `plan` CLI: deterministic, Monte Carlo, and historical cash-flow simulation with detailed US federal + Michigan tax modeling, driven by composable YAML scenarios. | This repo, installed with pip. |
| **Plugin** | A Claude Code plugin: an onboarding interview, a data-intake specialist, tax and retirement specialists, and hooks that inject the operator manual and auto-validate every config edit. | `plugins/finplan/` in this repo, installed with `/plugin`. |
| **Household directory** | Your plan: scenarios, balance snapshots, brokerage exports, run output, and a dated knowledge log. | Any folder you choose, created by `plan init`. Yours alone, never in this repo. |

The human never edits YAML by hand. You talk in plain English, paste numbers, or drop
brokerage exports into `inbox/`; Claude translates that into config and snapshot files,
runs the engine, and explains results. Agents advise, code computes: every dollar figure
comes from the engine, never from model arithmetic.

## Getting started

Once per machine:

```
python -m pip install "finplan @ git+https://github.com/jzdecourcy/finplan"
```

Then, inside Claude Code:

```
/plugin marketplace add jzdecourcy/finplan
/plugin install finplan@finplan
```

Once per household:

```
plan init ~/money          # scaffolds the household directory
cd ~/money
claude                     # the plugin wakes up here and injects its operator manual
```

and in that session run **`/finplan:interview`**, a phased, resumable onboarding
interview that builds `scenarios/base.yaml` and your first balance snapshot
conversationally. A fictional worked example is copied into every household directory,
so you can smoke-test the engine any time:

```
plan run -f scenarios/examples/base.yaml -f scenarios/examples/retire_55.yaml
```

Whether the household directory becomes a git repo is your call. If it does, keep it
private. `snapshots/`, `inbox/`, and `runs/` are already gitignored, and `plan check`
scans the rest for SSN and account-number patterns.

## Day to day

- **Monthly update:** drop an export in `inbox/` or paste balances; Claude writes
  `snapshots/<today>.yaml`, confirms the deltas, and runs `plan status`.
- **What-ifs:** overlays in `scenarios/overlays/` are small partial configs merged over
  base by `id` (`retire_55`, `ss_70`, `spend_plus30`). `plan compare` prices them side by
  side; `plan sweep` crosses the levers you control against the stresses you don't.
- **Taxes are computed, never estimated:** bracket walks, LTCG stacking, Social Security
  provisional income, RMDs, FICA, NIIT, QBI, ACA premium credits, Medicare IRMAA, Michigan
  flat tax with the retirement subtraction and 529 deduction. Parameters are per-year data
  files with cited primary sources, golden-tested against IRS worksheet examples.
- **Knowledge write-back:** every assumption, decision, durable fact, and open CPA question
  is appended to `knowledge/` with a date, so the next session starts where this one ended.

## Commands

```
plan init <dir> [--name X]   scaffold a household directory
plan context                  session-start summary: plan, data age, last run, knowledge activity
plan check                    overlay naming, every overlay validates over base, privacy scan
plan validate -f scenarios/base.yaml [-f overlay ...]
plan show-config -f base -f overlay --diff-base
plan run -f scenarios/base.yaml [--mode det|mc|hist] [--seed N] [--workers N] [-o runs/name]
plan compare -f scenarios/base.yaml --scenario "r55:-f scenarios/overlays/retire_55.yaml"
plan sweep -f scenarios/base.yaml --spec scenarios/sweeps/grid.yaml [--mode det] [-o runs/name]
plan update [brokerage-4321=462000 ...]   write today's snapshot
plan status                   net worth, data age, last run headline
plan tax-year --year 2026 --filing mfj --wages sam=95000 --wages riley=95000 --income business=250000
```

## How the plugin works

- `skills/interview` is the onboarding script; `agents/` holds the data-intake,
  tax-strategist, and retirement-planner specialists.
- `hooks/session_start.py` prints `manual.md` (the generic operator manual: ground rules,
  guardrails, conventions) plus `plan context` whenever Claude starts inside a household
  directory, and prints nothing anywhere else. The plugin can stay enabled globally.
- `hooks/post_edit.py` runs `plan validate` after any edit to base, an overlay, or a
  snapshot and feeds a failure straight back to the model.

Household-specific preferences (who decides, how to frame results) live in the household
directory's own short `CLAUDE.md`, which `plan init` writes as a template.

## Known limits

Federal + Michigan state tax only (other states: `state: none`, and adding one is a code
project with a cited parameter file and golden tests). Standard deduction only; no AMT;
average-cost basis; annual steps; one fixed allocation per account. This is a planning
tool, not tax advice. Consequential moves go through a human CPA via
`knowledge/open-questions.md`.

## Where it's headed

- Publish the engine to PyPI so the install is `pip install finplan`.
- More states, each as a module plus a cited parameter file and golden tests.
- An end-user narrative report ("your plan, explained") generated from a run directory.
- A leftover-529 haircut at the horizon and a per-account draw ladder for 529 plans.
- Plugin evals so the interview and specialists can be regression-tested.

## Development

```
git clone https://github.com/jzdecourcy/finplan && cd finplan
python -m pip install -e .[dev]
pytest
```

Plugin changes need a refresh of the installed copy:

```
claude plugin marketplace update finplan && claude plugin update finplan@finplan
```

See `CLAUDE.md` for the engine-development rules (sourced tax parameters, golden tests,
version bumps).
