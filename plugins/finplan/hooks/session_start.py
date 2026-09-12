"""SessionStart hook: inject the generic operator manual when Claude starts in a finplan
household directory. Stdout from a SessionStart hook is added to Claude's context.

Prints nothing outside a household directory. When the installed engine offers
`plan context` (live status: standing plan, data age, last run) its output follows the
manual; older engines just get the manual.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _common import household_dir, read_event  # noqa: E402

PLUGIN_ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    event = read_event()
    home = household_dir(event)
    if home is None:
        return 0
    out: list[str] = []
    manual = PLUGIN_ROOT / "manual.md"
    if manual.exists():
        out.append(manual.read_text(encoding="utf-8").rstrip())
    out.append(f"\nHousehold directory: {home}")
    if shutil.which("plan"):
        try:
            r = subprocess.run(["plan", "context"], cwd=home, capture_output=True,
                               text=True, timeout=15, encoding="utf-8", errors="replace")
            if r.returncode == 0 and r.stdout.strip():
                out.append("\n## Current state (plan context)\n")
                out.append(r.stdout.rstrip())
        except (subprocess.TimeoutExpired, OSError):
            pass
    else:
        out.append("\nWARNING: the `plan` CLI is not on PATH. Install the engine: "
                   "`python -m pip install finplan` (or `pip install -e <engine checkout>`).")
    sys.stdout.reconfigure(encoding="utf-8")
    print("\n".join(out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
