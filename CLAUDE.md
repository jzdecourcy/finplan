# finplan — engine and plugin repo (developer notes for Claude sessions)

This repo is the **framework**: the `plan` engine (`src/finplan`), its tests, and the
Claude Code plugin (`plugins/finplan`) served from the marketplace manifest at
`.claude-plugin/marketplace.json`. It contains no household data and never will. A
household's plan lives in a separate directory created by `plan init`; the operator
manual for working there is `plugins/finplan/manual.md`, not this file.

## Rules

1. **No personal data.** No real names, balances, incomes, account labels, or run output.
   Examples are fictional (`src/finplan/data/examples/`, household templates in
   `src/finplan/data/household/`). If a fix needs a real household's config to reproduce,
   rebuild the case as a fixture with fictional numbers.
2. **Tax parameter files** (`src/finplan/data/tax/`) change only with a cited primary
   source in their `sources:` block and passing golden tests (`tests/golden/`). Never edit
   them from memory.
3. **Engine results are golden-tested.** `tests/golden/sim_snapshots` pins a full lifetime
   run; re-bless with `pytest --update-golden` only when a change is meant to move numbers,
   and say what moved and why in the commit.
4. **Every household-facing convention lives in one place.** Mechanical rules go into
   `plan check` (naming, validation, privacy scan); behavioural rules go into
   `plugins/finplan/manual.md`. Don't restate either in skills or agents.
5. **Version bumps** touch `pyproject.toml`, `src/finplan/__init__.py`,
   `plugins/finplan/.claude-plugin/plugin.json`, and `.claude-plugin/marketplace.json`
   together.

## Layout

```
src/finplan/            engine: config loader, simulation, taxes, policies, reports, CLI
src/finplan/data/       tax parameters, market/SS data, example plans, household templates
tests/                  unit + golden tests (self-contained, no household directory needed)
plugins/finplan/        the Claude Code plugin: skills/, agents/, hooks/, manual.md
.claude-plugin/         marketplace manifest listing plugins/finplan
```

## Commands

```
python -m pip install -e .[dev]
pytest
plan init <scratch-dir>                      # exercise the household flow end to end
claude plugin marketplace add C:/path/to/finplan   # once, local dev marketplace
claude plugin install finplan@finplan
claude plugin marketplace update finplan && claude plugin update finplan@finplan   # after plugin edits
claude plugin details finplan@finplan        # component inventory and token cost
```

## Hooks

`hooks/hooks.json` wires `session_start.py` (prints `manual.md` + `plan context` in a
household directory, nothing elsewhere) and `post_edit.py` (runs `plan validate` after a
Write/Edit to base, an overlay, or a snapshot; exit 2 with the validator's message on
failure). Test them by piping a fake event: `echo '{"cwd":"<dir>"}' | python hooks/session_start.py`.
