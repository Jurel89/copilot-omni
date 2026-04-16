#!/usr/bin/env python3
"""Session start hook — prints a banner and exits."""

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
import sys


def main() -> int:
    banner = (
        "Copilot Omni v1.0.0 — enterprise-safe multi-agent orchestration. "
        "29 MCP tools, 28+ skills, 17+ agents. Pure Python stdlib. "
        "Run /omni-init to scaffold .omni/ in this project."
    )
    payload = {"additionalContext": banner}
    sys.stdout.write(json.dumps(payload))
    sys.stdout.flush()
    return 0


if __name__ == "__main__":
    sys.exit(main())
