"""CLI entry point. Thin layer: parse args, call finplan.api, print/report."""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import click
import yaml

from finplan import __version__
from finplan.config.loader import ConfigError, load_scenario


def _config_files(files: tuple[str, ...]) -> list[str]:
    if not files:
        default = Path("scenarios/base.yaml")
        if default.exists():
            return [str(default)]
        raise click.UsageError("no -f given and scenarios/base.yaml not found")
    return list(files)


@click.group()
@click.version_option(__version__, prog_name="plan")
def cli() -> None:
    """finplan — personal financial planning and scenario modeling."""


@cli.command()
@click.option("-f", "--file", "files", multiple=True, type=click.Path(exists=True))
def validate(files: tuple[str, ...]) -> None:
    """Compose and validate config files (base + overlays, left to right)."""
    try:
        cfg, _, snap = load_scenario(_config_files(files))
    except ConfigError as e:
        raise click.ClickException(str(e)) from None
    click.echo(f"OK: scenario '{cfg.meta.name}' is valid "
               f"({len(cfg.accounts)} accounts, {len(cfg.income)} income streams, "
               f"{len(cfg.expenses)} expense streams, {len(cfg.events)} events)")
    if snap:
        click.echo(f"balances from snapshot: {snap}")
    from finplan.engine.build import derived_pias  # noqa: PLC0415

    for name, pia in derived_pias(cfg).items():
        entered = next(p.ss_pia_monthly for p in cfg.household.people if p.name == name)
        note = f" (replaces entered ${entered:,.0f})" if entered else ""
        click.echo(f"recomputed SS PIA from earnings history: {name} "
                   f"${pia:,.2f}/mo in today's dollars{note}")


@cli.command("show-config")
@click.option("-f", "--file", "files", multiple=True, type=click.Path(exists=True))
@click.option("--diff-base", is_flag=True, help="show only what overlays changed vs. the first file")
def show_config(files: tuple[str, ...], diff_base: bool) -> None:
    """Print the fully composed scenario config."""
    files = _config_files(files)
    try:
        _, resolved, _ = load_scenario(files)
    except ConfigError as e:
        raise click.ClickException(str(e)) from None
    if diff_base and len(files) > 1:
        import difflib

        base_only, _, _ = load_scenario(files[:1])
        base_text = yaml.safe_dump(yaml.safe_load(Path(files[0]).read_text(encoding="utf-8")),
                                   sort_keys=False)
        resolved_text = yaml.safe_dump(resolved, sort_keys=False)
        diff = difflib.unified_diff(base_text.splitlines(), resolved_text.splitlines(),
                                    "base", "resolved", lineterm="")
        click.echo("\n".join(diff) or "(no differences)")
    else:
        click.echo(yaml.safe_dump(resolved, sort_keys=False))


@cli.command()
@click.option("-f", "--file", "files", multiple=True, type=click.Path(exists=True))
@click.option("--mode", type=click.Choice(["det", "mc", "hist"]), default="det")
@click.option("--seed", type=int, default=None)
@click.option("--paths", "n_paths", type=int, default=None, help="Monte Carlo path count")
@click.option("-o", "--out", "out_dir", type=click.Path(), default=None,
              help="write ledger.csv, metrics.json, charts to this directory")
@click.option("--workers", type=int, default=None,
              help="processes to split MC paths across (default: auto, cpus-2)")
@click.option("--every", type=int, default=1, help="print every Nth year only")
def run(files, mode, seed, n_paths, out_dir, workers, every) -> None:
    """Run a scenario and print the annual ledger (det) or summary metrics (mc/hist)."""
    from finplan.api import run_scenario
    from finplan.report.tables import annual_summary

    if out_dir is None:
        stamp = dt.date.today().isoformat()
        out_dir = f"runs/{stamp}-{mode}"
    try:
        results = run_scenario(_config_files(files), mode=mode, seed=seed,
                               n_paths=n_paths, out_dir=out_dir, workers=workers)
    except ConfigError as e:
        raise click.ClickException(str(e)) from None
    _print_staleness()
    if results.n_paths == 1:
        click.echo(annual_summary(results, every=every))
    m = results.metrics()
    click.echo("")
    for k, v in m.items():
        click.echo(f"{k:>32}: {v}")
    click.echo(f"\noutputs -> {out_dir}")


@cli.command()
@click.option("-f", "--file", "files", multiple=True, type=click.Path(exists=True))
@click.option("--scenario", "scenarios", multiple=True,
              help='additional scenario as "name:-f overlay.yaml [-f more.yaml]"; '
                   "the bare -f stack runs as 'base'")
@click.option("--mode", type=click.Choice(["det", "mc", "hist"]), default="det")
@click.option("--seed", type=int, default=None)
@click.option("--paths", "n_paths", type=int, default=None)
@click.option("--workers", type=int, default=None,
              help="processes to split MC paths across (default: auto, cpus-2)")
@click.option("-o", "--out", "out_dir", type=click.Path(), default=None)
def compare(files, scenarios, mode, seed, n_paths, workers, out_dir) -> None:
    """Run several scenario stacks and produce a side-by-side comparison report."""
    import shlex

    from finplan.api import run_scenario
    from finplan.report.compare import NamedResults, comparison_table, write_report

    base_files = _config_files(files)
    stacks: list[tuple[str, list[str]]] = [("base", base_files)]
    for spec in scenarios:
        name, _, rest = spec.partition(":")
        if not rest:
            raise click.UsageError(f'bad --scenario {spec!r}; expected "name:-f file.yaml"')
        tokens = shlex.split(rest)
        extra = [tokens[i + 1] for i, t in enumerate(tokens) if t in ("-f", "--file")]
        if not extra:
            raise click.UsageError(f"--scenario {name!r} has no -f files")
        stacks.append((name, base_files + extra))
    if out_dir is None:
        out_dir = f"runs/{dt.date.today().isoformat()}-compare"
    runs = []
    notes = {}
    for name, stack in stacks:
        try:
            results = run_scenario(stack, mode=mode, seed=seed, n_paths=n_paths,
                                   workers=workers)
        except ConfigError as e:
            raise click.ClickException(f"scenario {name!r}: {e}") from None
        runs.append(NamedResults(name=name, results=results))
        notes[name] = " + ".join(Path(f).name for f in stack)
    report = write_report(runs, out_dir, mode, notes)
    _print_staleness()
    click.echo(comparison_table(runs).to_string())
    click.echo(f"\nreport -> {report}")


@cli.command()
@click.option("-f", "--file", "files", multiple=True, type=click.Path(exists=True))
@click.option("--spec", "spec_path", required=True, type=click.Path(exists=True),
              help="sweep spec YAML (see scenarios/sweeps/)")
@click.option("--mode", type=click.Choice(["det", "mc", "hist"]), default=None,
              help="override the spec's mode (det is a fast smoke pass)")
@click.option("--seed", type=int, default=None, help="override the spec's seed")
@click.option("--paths", "n_paths", type=int, default=None, help="override the spec's MC path count")
@click.option("--workers", type=int, default=None, help="parallel processes (default: cpus-2)")
@click.option("-o", "--out", "out_dir", type=click.Path(), default=None)
def sweep(files, spec_path, mode, seed, n_paths, workers, out_dir) -> None:
    """Cross a grid of decision overlays under several stress conditions; report the frontier."""
    from finplan.sweep import enumerate_cells, load_spec, run_sweep

    try:
        spec = load_spec(spec_path)
    except ConfigError as e:
        raise click.ClickException(str(e)) from None
    if mode:
        spec.mode = mode
    if seed is not None:
        spec.seed = seed
    if n_paths is not None:
        spec.paths = n_paths
    if out_dir is None:
        out_dir = f"runs/{dt.date.today().isoformat()}-sweep-{spec.name}"
    n_cells = len(enumerate_cells(spec))
    click.echo(f"sweep {spec.name}: {n_cells} cells x {len(spec.stress)} stress conditions "
               f"= {n_cells * len(spec.stress)} runs ({spec.mode}, seed {spec.seed}, "
               f"paths {spec.paths or 'config'})")

    def progress(i, n):
        if i == n or i % max(1, n // 20) == 0:
            click.echo(f"  {i}/{n}", err=True)

    try:
        res = run_sweep(_config_files(files), spec, out_dir, workers=workers, progress=progress)
    except ConfigError as e:
        raise click.ClickException(str(e)) from None
    pd_opts = {"display.width": 200, "display.max_columns": 30, "display.max_rows": 200}
    import pandas as pd

    hide = ["frontier", "frontier_within", "first_failure"]
    with pd.option_context(*[x for kv in pd_opts.items() for x in kv]):
        click.echo("\n== global frontier (worst-case success vs. reference median terminal) ==")
        click.echo(res["frontier"].drop(columns=hide).to_string())
        w = res["within"]
        click.echo(f"\n== lookup: best cell per {w}, success under each stress condition ==")
        click.echo(res["lookup"].to_string())
        click.echo(f"\n== frontier within each {w} (the real choice set at that {w}) ==")
        click.echo(res["frontier_within"].drop(columns=hide).to_string())
        click.echo("\n== main effects (average over all other levers) ==")
        click.echo(res["effects"].to_string())
        if res["noise"] is not None:
            click.echo("\n== MC noise on top frontier cells (reference condition, extra seeds) ==")
            click.echo(res["noise"].to_string())
    m = res["meta"]
    click.echo(f"\n{m['runs']} runs in {m['seconds']}s on {m['workers']} workers -> {out_dir}")


@cli.command("tax-year")
@click.option("--year", type=int, default=2026)
@click.option("--filing", type=click.Choice(["single", "mfj"]), default="mfj")
@click.option("--state", type=click.Choice(["none", "michigan"]), default="michigan")
@click.option("--age", "ages", multiple=True, type=int, help="repeat per person")
@click.option("--income", "income_parts", multiple=True,
              help="component=amount, e.g. wages=180000 ltcg=20000 ss=40000 trad=30000 "
                   "conversion=25000 interest=1000 usgov=2000 qdiv=5000 mi529=10000 "
                   "aca_premium=24000 aca_hh=2 business=250000")
@click.option("--wages", "wages_parts", multiple=True,
              help="per-earner W-2 wages for FICA, name=amount (repeat); "
                   "replaces --income wages=")
@click.option("--qbi-wage-cap", type=float, default=None,
              help="s199A wage cap = 50%% of allocable W-2 wages (Statement A); "
                   "omit = no QBI deduction")
def tax_year(year, filing, state, ages, income_parts, wages_parts, qbi_wage_cap) -> None:
    """One-off tax calculation (debugging / trust-building)."""
    from finplan.model.household import FilingStatus
    from finplan.taxes.engine import compute_year_tax, marginal_rate
    from finplan.taxes.params import load_federal, load_michigan
    from finplan.taxes.types import TaxInput

    field_map = {
        "wages": "wages", "business": "business", "interest": "interest",
        "dividends": "ordinary_dividends", "qdiv": "qualified_dividends",
        "ltcg": "realized_ltcg", "stcg": "realized_stcg",
        "trad": "traditional_distributions", "conversion": "roth_conversions",
        "ss": "ss_benefits", "penalty": "penalty_base", "mi529": "mi_529_contributions",
        "muni": "tax_exempt_interest", "usgov": "us_gov_interest",
        "aca_premium": "aca_benchmark_premium", "aca_hh": "aca_household_size",
    }
    kwargs: dict = {}
    for part in income_parts:
        k, _, v = part.partition("=")
        if k not in field_map:
            raise click.UsageError(f"unknown component {k!r}; one of {sorted(field_map)}")
        kwargs[field_map[k]] = float(v.replace(",", ""))
    if "aca_household_size" in kwargs:
        kwargs["aca_household_size"] = int(kwargs["aca_household_size"])
    age_list = list(ages) or ([45, 45] if filing == "mfj" else [45])
    wages_by_person: dict[str, float] = {}
    for part in wages_parts:
        name, _, v = part.partition("=")
        if not v:
            raise click.UsageError(f"--wages expects name=amount, got {part!r}")
        wages_by_person[name] = wages_by_person.get(name, 0.0) + float(v.replace(",", ""))
    if wages_by_person:
        if kwargs.get("wages"):
            raise click.UsageError("use either --wages name=amount or --income wages=, not both")
        kwargs["wages"] = sum(wages_by_person.values())
    elif kwargs.get("wages"):
        wages_by_person = {"p0": kwargs["wages"]}
    inp = TaxInput(
        year=year, filing_status=FilingStatus(filing),
        ages={f"p{i}": a for i, a in enumerate(age_list)},
        wages_by_person=wages_by_person,
        qbi_wage_cap=qbi_wage_cap,
        **kwargs,
    )
    try:
        params = load_federal(year)
    except FileNotFoundError:
        raise click.ClickException(f"no federal parameter file for {year}") from None
    mi = load_michigan(year) if state == "michigan" else None
    r = compute_year_tax(inp, params, mi)
    click.echo(f"tax year {year}, filing {filing}, state {state}")
    rows = [
        ("AGI", r.agi), ("taxable income", r.taxable_income),
        ("taxable Social Security", r.taxable_ss), ("federal income tax", r.federal),
        ("FICA", r.fica), ("penalties", r.penalties), ("Michigan tax", r.state),
        ("TOTAL", r.total),
    ]
    if qbi_wage_cap is not None:
        rows[2:2] = [("QBI deduction", r.qbi_deduction)]
    if kwargs.get("aca_benchmark_premium"):
        rows[3:3] = [("ACA MAGI", r.aca_magi), ("ACA premium credit", r.aca_credit)]
    for label, v in rows:
        click.echo(f"  {label:>24}: ${v:,.0f}")
    if kwargs.get("aca_benchmark_premium"):
        click.echo(f"  {'ACA % of FPL':>24}: {r.aca_fpl_pct:.1%}")
    mo = marginal_rate(inp, params, mi, "ordinary")
    ml = marginal_rate(inp, params, mi, "ltcg")
    click.echo(f"  {'marginal (ordinary)':>24}: {mo:.1%}")
    click.echo(f"  {'marginal (LTCG)':>24}: {ml:.1%}")


def _snapshot_dir() -> Path:
    return Path("snapshots")


def _latest_snapshot() -> tuple[Path | None, dict]:
    d = _snapshot_dir()
    files = sorted(d.glob("*.yaml")) if d.exists() else []
    if not files:
        return None, {}
    data = yaml.safe_load(files[-1].read_text(encoding="utf-8")) or {}
    return files[-1], data.get("accounts", data)


def _print_staleness() -> None:
    path, _ = _latest_snapshot()
    if path is None:
        return
    snap_date = dt.date.fromisoformat(path.stem)
    age = (dt.date.today() - snap_date).days
    msg = f"balance snapshot: {path.stem} ({age} days old)"
    if age > 60:
        msg += "  << stale - consider `plan update`"
    click.echo(msg + "\n")


@cli.command()
@click.argument("updates", nargs=-1)
def update(updates: tuple[str, ...]) -> None:
    """Refresh account balances into a dated snapshot.

    With args: `plan update brokerage=462000 401k-j=615000`.
    Without args: interactive walk-through (Enter keeps the previous value).
    """
    prev_path, prev = _latest_snapshot()
    accounts: dict[str, dict] = {
        k: (dict(v) if isinstance(v, dict) else {"balance": float(v)})
        for k, v in prev.items()
    }
    if not accounts:
        try:
            cfg, _, _ = load_scenario([str(Path("scenarios/base.yaml"))])
            accounts = {a.id: {"balance": a.balance} for a in cfg.accounts}
        except ConfigError:
            raise click.ClickException(
                "no previous snapshot and no scenarios/base.yaml to seed account list"
            ) from None
    if updates:
        for u in updates:
            if "=" not in u:
                raise click.UsageError(f"expected id=balance, got {u!r}")
            acct_id, val = u.split("=", 1)
            accounts.setdefault(acct_id, {})["balance"] = float(val.replace(",", "").replace("$", ""))
    else:
        click.echo("Enter new balances (Enter keeps previous):")
        for acct_id, vals in accounts.items():
            prev_bal = vals.get("balance", 0.0)
            raw = click.prompt(f"  {acct_id} [{prev_bal:,.0f}]", default="", show_default=False)
            if raw.strip():
                vals["balance"] = float(raw.replace(",", "").replace("$", ""))
    d = _snapshot_dir()
    d.mkdir(exist_ok=True)
    out = d / f"{dt.date.today().isoformat()}.yaml"
    out.write_text(yaml.safe_dump({"accounts": accounts}, sort_keys=False), encoding="utf-8")
    click.echo(f"wrote {out}")
    if prev_path:
        for acct_id, vals in accounts.items():
            old = prev.get(acct_id, {})
            old_bal = old.get("balance") if isinstance(old, dict) else old
            new_bal = vals.get("balance")
            if old_bal is not None and new_bal is not None and old_bal != new_bal:
                click.echo(f"  {acct_id}: {old_bal:,.0f} -> {new_bal:,.0f} ({new_bal - old_bal:+,.0f})")


@cli.command()
def status() -> None:
    """One-screen check-in: net worth from latest snapshot, data age, last run metrics."""
    path, accounts = _latest_snapshot()
    if path is None:
        click.echo("no snapshots yet - run `plan update` or start from scenarios/base.yaml")
    else:
        total = sum(
            (v.get("balance", 0.0) if isinstance(v, dict) else float(v))
            for v in accounts.values()
        )
        age = (dt.date.today() - dt.date.fromisoformat(path.stem)).days
        click.echo(f"net worth (snapshot {path.stem}, {age}d old): ${total:,.0f}")
        for acct_id, v in accounts.items():
            bal = v.get("balance", 0.0) if isinstance(v, dict) else float(v)
            click.echo(f"  {acct_id:>16}: ${bal:,.0f}")
    runs = sorted(Path("runs").glob("*/metrics.json")) if Path("runs").exists() else []
    if runs:
        import json

        m = json.loads(runs[-1].read_text(encoding="utf-8"))
        click.echo(f"\nlast run ({runs[-1].parent.name}):")
        for k, v in m.items():
            click.echo(f"  {k}: {v}")


if __name__ == "__main__":
    cli()
