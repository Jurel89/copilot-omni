#!/usr/bin/env python3
"""Post-tool-use hook — best-effort audit log. Never blocks."""
from __future__ import annotations

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
