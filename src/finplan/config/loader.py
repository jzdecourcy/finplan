"""Load + compose + snapshot-resolve + validate scenario configs."""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import ValidationError

from finplan.config.compose import compose
from finplan.config.schema import ScenarioConfig


class ConfigError(Exception):
    pass


def load_yaml(path: str | Path) -> dict:
    p = Path(path)
    if not p.exists():
        raise ConfigError(f"config file not found: {p}")
    data = yaml.safe_load(p.read_text(encoding="utf-8"))
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise ConfigError(f"{p}: top level must be a mapping")
    return data


def _resolve_snapshot_ref(ref: str, root: Path) -> Path:
    """'snapshots/latest' -> newest dated file; otherwise treat as a path."""
    if ref.endswith("/latest") or ref.endswith("\\latest"):
        snap_dir = root / Path(ref).parent
        candidates = sorted(snap_dir.glob("*.yaml")) + sorted(snap_dir.glob("*.yml"))
        if not candidates:
            raise ConfigError(f"no snapshot files in {snap_dir}")
        return candidates[-1]  # dated YYYY-MM-DD names sort chronologically
    p = root / ref
    if not p.exists():
        raise ConfigError(f"snapshot not found: {p}")
    return p


def apply_snapshot(resolved: dict, root: Path) -> tuple[dict, Path | None]:
    """Merge balances/cost_basis from the accounts_from snapshot into account entries."""
    ref = resolved.get("accounts_from")
    if not ref:
        return resolved, None
    snap_path = _resolve_snapshot_ref(ref, root)
    snap = yaml.safe_load(snap_path.read_text(encoding="utf-8")) or {}
    accounts_data = snap.get("accounts", snap)  # allow flat {id: {...}} or {accounts: {...}}
    if not isinstance(accounts_data, dict):
        raise ConfigError(f"{snap_path}: expected mapping of account id -> {{balance, cost_basis}}")
    by_id = {a["id"]: a for a in resolved.get("accounts", [])}
    for acct_id, values in accounts_data.items():
        if acct_id == "date":
            continue
        if acct_id not in by_id:
            raise ConfigError(
                f"{snap_path}: snapshot has account {acct_id!r} not present in scenario config"
            )
        if isinstance(values, dict):
            by_id[acct_id].update({k: v for k, v in values.items() if k in ("balance", "cost_basis")})
        else:  # bare number = balance
            by_id[acct_id]["balance"] = float(values)
    return resolved, snap_path


def load_scenario(
    paths: list[str | Path], root: str | Path | None = None
) -> tuple[ScenarioConfig, dict, Path | None]:
    """Compose config files left-to-right; returns (validated, resolved_dict, snapshot_path)."""
    if not paths:
        raise ConfigError("at least one config file required")
    root = Path(root) if root else Path(paths[0]).resolve().parent.parent
    docs = [load_yaml(p) for p in paths]
    resolved = compose(docs[0], *docs[1:])
    resolved, snap_path = apply_snapshot(resolved, root)
    payload = {k: v for k, v in resolved.items() if k != "accounts_from"}
    try:
        cfg = ScenarioConfig.model_validate(payload)
    except ValidationError as e:
        raise ConfigError(str(e)) from None
    return cfg, resolved, snap_path
