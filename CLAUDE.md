# finplan — operator's manual for Claude sessions

This repo is a personal financial planning environment. **Claude is the primary interface**:
the user never edits YAML by hand. They talk in plain English, paste numbers, or drop
brokerage CSV exports into `inbox/`. Claude translates that into config/snapshot files,
runs the engine, and explains results.

## Ground rules

1. **Agents advise, code computes.** All dollar figures come from the engine (`plan run`,
   `plan tax-year`), never from model arithmetic. Never hand-estimate a tax or projection result.
2. **Privacy**: `snapshots/`, `inbox/`, and `runs/` are gitignored and must stay that way.
   Never commit real balances. Never write SSNs, full account numbers, or institution logins
   anywhere — strip account numbers to a last-4 label (e.g. `fidelity-4321`). The user's
   instance of this repo must be private: `scenarios/` and `knowledge/` are version-controlled
   on purpose and accumulate personal detail (names, salaries — never balances).
3. **Every config edit is reviewed as English + a diff**: after editing scenario files, run
   `plan validate` and show the user what changed and why (`plan show-config --diff-base`).
4. **Tax parameter files** (`src/finplan/data/tax/`) change only with a cited primary source
   (`sources:` block) and passing golden tests. Never edit them from memory.
5. **Write-back discipline**: after any session that sets an assumption, makes a decision, or
   learns a durable household fact, append it to the matching file in `knowledge/` with a date.
   Consequential moves (large Roth conversions, sales) go on `knowledge/open-questions.md` for
   a human CPA — the model does not give tax advice.

## File conventions

- `scenarios/base.yaml` — the user's base plan (structure: household, accounts, income,
  expenses, policies, market). Account *balances* live in snapshots, not here.
- `scenarios/examples/` — fictional sample configs, safe to commit; a starting template.
- `scenarios/overlays/*.yaml` — partial configs merged over base (`-f base -f overlay`).
  List items merge by `id`; `remove: true` deletes an item; scalars replace.
  **Naming**: stem = `<family>_<value>` snake_case (`retire_57`, `roth_ladder_22`,
  `move_2030_mortgage`, `ss_70`, `spend_plus30`); `meta.name` equals the stem;
  `meta.description` is a required one-liner (quote it if it contains a colon). The
  first comment lines stay for the long story. `tests/unit/test_overlay_naming.py`
  enforces this. Typical families: retire, ss, horizon, spend, earn, roth_ladder,
  withdraw, guardrail, contrib, cash, move, aca.
- `scenarios/sweeps/*.yaml` — sweep specs for `plan sweep`: `levers` (choices the
  household controls, crossed) and `stress` (assumptions it doesn't, each cell re-run
  under every one; first entry = reference). Classify a new overlay family as lever or
  stress before adding it. `--mode det` is a seconds-long smoke pass; MC on a ~150-cell
  grid takes ~15 min on a desktop. Read the per-lever lookup and within-lever frontier,
  not the global frontier (the global one is always captured by "retire later").
- `snapshots/YYYY-MM-DD.yaml` — dated per-account `{balance, cost_basis}` values.
  `accounts_from: snapshots/latest` in base.yaml resolves to the newest file.
- `inbox/` — user drops CSV position exports here; parse into a snapshot, confirm with the
  user, then move the file to `inbox/processed/`, **renaming it on the way**:
  `YYYY-MM-DD_institution-last4-owner_doctype[-period].ext` (lowercase; date = pull date;
  doctype ∈ positions / holdings / balance / activity / annual-summary / benefit-estimate;
  add a period suffix like `activity-2025` when the file covers a span other than the pull
  date). Example: `2026-09-03_fidelity-4321-sam-roth_positions.csv`. Multi-account exports use `<institution>-all-accounts`; joint or owner-less accounts use `-joint` in place of the owner. Renaming also strips
  any full account numbers from raw export filenames (privacy rule #2).
- `knowledge/` — assumptions.md, decisions.md, facts.md, open-questions.md (see write-back rule).
- `knowledge/glossary.md` — plain-English definitions of report/plan terms. Keep it
  current: when a report or conversation introduces a term the user might not know,
  add it there (short entries, no balances) rather than re-explaining each session.
- `knowledge/data-sources.md` — per-institution playbook for pulling balances (export
  paths, gotchas, account rosters). Read it BEFORE asking the user how to get data;
  update it when an institution's process changes.

## Commands

```
python -m pip install -e .[dev]     # first-time setup
pytest                              # run tests (golden tax cases are the correctness backstop)
plan validate -f scenarios/base.yaml [-f overlay ...]
plan run -f scenarios/base.yaml [--mode det|mc|hist] [--seed N] [-o runs/name]
plan compare -f base.yaml --scenario "name:-f overlay.yaml" ...
plan sweep -f base.yaml --spec scenarios/sweeps/<grid>.yaml [--mode det] [-o runs/name]
                                    # cross decision levers x stress conditions; frontier report
plan update [account=balance ...]   # write today's snapshot
plan status                         # net worth, data age, last run headline
plan tax-year --year 2026 --filing mfj --income wages=180000 ...
```

## Step 0 onboarding (first session, or re-onboarding after a life change)

Run the `/interview` skill (`.claude/skills/interview/SKILL.md`) — the full phased
interview script, generic for any household, resumable via
`knowledge/onboarding-status.md`. The script is the single source of truth for
onboarding; don't restate its checklist here.

## Monthly update checklist

1. Parse whatever the user provides (inbox CSVs, pasted numbers, or run `plan update`).
2. Write `snapshots/<today>.yaml`; confirm the deltas with the user.
3. `plan status` and report anything notable vs. the plan.

## Known engine limits

Federal + Michigan state tax only (other states: set `state: none`, warn the user, and
log it in assumptions — adding a state is a code project: module under
`src/finplan/taxes/`, cited parameter file under `src/finplan/data/tax/`, golden tests).
Standard deduction only; no AMT; average-cost basis; no loss carryforwards; annual steps.
`plan tax-year` has no QBI option and puts all wages on one earner (use it for W-2-only
sanity checks; business owners reconcile via a `plan run` year-1 ledger). Contribution
policies have no start/end dates. Education expenses draw from 529s in config order,
ignoring beneficiary. Cash accounts grow at the modeled cash return, not their APY.
