#!/usr/bin/env python3
"""Session start hook — prints a banner and exits."""
import json
import os
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
