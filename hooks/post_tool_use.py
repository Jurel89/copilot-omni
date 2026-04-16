#!/usr/bin/env python3
"""Post-tool-use hook — best-effort audit log. Never blocks."""

# ---------------------------------------------------------------------------
# Kill-switch: OMNI_SKIP_HOOKS=1 or DISABLE_OMNI=1 disables this hook.
# Backward-compat aliases: OMC_SKIP_HOOKS and DISABLE_OMC are honoured
# during the deprecation window and will be removed in v3.0.0.
# ---------------------------------------------------------------------------
import os as _os
if (_os.environ.get("OMNI_SKIP_HOOKS") or _os.environ.get("DISABLE_OMNI")
        or _os.environ.get("OMC_SKIP_HOOKS") or _os.environ.get("DISABLE_OMC")):
    import sys as _sys
    _sys.stdout.write("{}")
    _sys.stdout.flush()
    _sys.exit(0)
del _os

import json
import os
import sys
import time
from pathlib import Path


def main() -> int:
    try:
        event = json.loads(sys.stdin.read() or "{}")
    except Exception:
        event = {}
    try:
        cwd = Path(os.getcwd())
        log_dir = cwd / ".omni" / "audit"
        log_dir.mkdir(parents=True, exist_ok=True)
        entry = {
            "ts": time.time(),
            "tool": event.get("tool_name") or event.get("toolName"),
            "status": event.get("status", "completed"),
        }
        with (log_dir / "tool-audit.log").open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
    except Exception:
        pass
    sys.stdout.write("{}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
