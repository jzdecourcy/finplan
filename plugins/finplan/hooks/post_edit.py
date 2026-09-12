"""PostToolUse hook (Write|Edit): after Claude edits a scenario or snapshot file inside a
household directory, run `plan validate` on it so a broken config is caught immediately.

- scenarios/base.yaml            -> plan validate -f scenarios/base.yaml
- scenarios/overlays/<x>.yaml    -> plan validate -f scenarios/base.yaml -f <x>
- snapshots/<date>.yaml          -> plan validate -f scenarios/base.yaml (accounts_from latest)
- anything else                  -> silent

On failure the validator's message goes to stderr with exit code 2, which Claude Code
feeds back to the model as an error to fix. On success a one-line confirmation goes to
stdout (visible in the transcript).
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _common import household_dir, read_event  # noqa: E402


def main() -> int:
    event = read_event()
    home = household_dir(event)
    if home is None:
        return 0
    raw = (event.get("tool_input") or {}).get("file_path")
    if not raw:
        return 0
    path = Path(raw)
    if not path.is_absolute():
        path = home / path
    try:
        rel = path.resolve().relative_to(home)
    except ValueError:
        return 0
    if rel.suffix not in (".yaml", ".yml"):
        return 0
    base = home / "scenarios" / "base.yaml"
    if not base.exists():
        return 0
    parts = rel.parts
    if parts[:1] == ("snapshots",) or rel == Path("scenarios/base.yaml"):
        files = [base]
    elif parts[:2] == ("scenarios", "overlays"):
        files = [base, home / rel]
    else:
        return 0
    if not shutil.which("plan"):
        print("finplan hook: `plan` not on PATH, skipped validation", file=sys.stderr)
        return 0
    cmd = ["plan", "validate"]
    for f in files:
        cmd += ["-f", str(f.relative_to(home))]
    r = subprocess.run(cmd, cwd=home, capture_output=True, text=True, timeout=80,
                       encoding="utf-8", errors="replace")
    if r.returncode != 0:
        sys.stderr.write(f"plan validate FAILED for {rel}:\n{r.stdout}{r.stderr}")
        return 2
    print(f"plan validate OK: {' '.join(cmd[2:])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
