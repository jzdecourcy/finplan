import textwrap

import pytest

from finplan.config.loader import ConfigError, load_scenario

BASE = """
sim: { start_year: 2030, horizon: 2032 }
household:
  filing_status: single
  people: [{ name: sam, birth_year: 1980 }]
accounts_from: snapshots/latest
accounts:
  - { id: cash, type: cash, balance: 1 }
  - { id: brokerage, type: taxable, balance: 1 }
income: []
expenses: [{ id: living, annual: 10, start: 2030, end: 2032 }]
taxes: { regime: flat_stub }
"""


def _write(tmp_path, rel, text):
    p = tmp_path / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(textwrap.dedent(text), encoding="utf-8")
    return p


def test_snapshot_latest_resolution(tmp_path):
    base = _write(tmp_path, "scenarios/base.yaml", BASE)
    _write(tmp_path, "snapshots/2026-01-01.yaml",
           "accounts: { cash: { balance: 111 }, brokerage: { balance: 222, cost_basis: 100 } }")
    _write(tmp_path, "snapshots/2026-03-01.yaml",
           "accounts: { cash: { balance: 999 }, brokerage: { balance: 888, cost_basis: 500 } }")
    cfg, _, snap = load_scenario([base], root=tmp_path)
    assert snap.name == "2026-03-01.yaml"  # newest dated file wins
    by_id = {a.id: a for a in cfg.accounts}
    assert by_id["cash"].balance == 999
    assert by_id["brokerage"].balance == 888
    assert by_id["brokerage"].cost_basis == 500


def test_snapshot_unknown_account_rejected(tmp_path):
    base = _write(tmp_path, "scenarios/base.yaml", BASE)
    _write(tmp_path, "snapshots/2026-01-01.yaml", "accounts: { mystery: 5 }")
    with pytest.raises(ConfigError, match="mystery"):
        load_scenario([base], root=tmp_path)


def test_missing_snapshot_dir_errors(tmp_path):
    base = _write(tmp_path, "scenarios/base.yaml", BASE)
    with pytest.raises(ConfigError, match="no snapshot"):
        load_scenario([base], root=tmp_path)


def test_no_accounts_from_is_fine(tmp_path):
    base = _write(tmp_path, "scenarios/base.yaml", BASE.replace("accounts_from: snapshots/latest\n", ""))
    cfg, _, snap = load_scenario([base], root=tmp_path)
    assert snap is None
    assert cfg.accounts[0].balance == 1


def test_validation_error_reports_cleanly(tmp_path):
    bad = BASE.replace("filing_status: single", "filing_status: royalty")
    base = _write(tmp_path, "scenarios/base.yaml", bad.replace("accounts_from: snapshots/latest\n", ""))
    with pytest.raises(ConfigError):
        load_scenario([base], root=tmp_path)
