#!/usr/bin/env python3
"""Plugin discovery smoke: verifies filesystem layout matches Copilot CLI
discovery rules — manifest in .claude-plugin/plugin.json, skills/ directory
with SKILL.md files, agents/ with .md files, commands/ with .md files,
hooks/hooks.json and .mcp.json reachable.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    failures = []

    manifest = ROOT / ".claude-plugin" / "plugin.json"
    if not manifest.exists():
        failures.append("missing .claude-plugin/plugin.json")
    else:
        data = json.loads(manifest.read_text(encoding="utf-8"))
        for field in ("name", "version", "description"):
            if field not in data:
                failures.append(f"plugin.json missing '{field}'")
        if data.get("name") != "copilot-omni":
            failures.append(f"unexpected plugin name: {data.get('name')!r}")

    mcp = ROOT / ".mcp.json"
    if not mcp.exists():
        failures.append("missing .mcp.json")

    hooks = ROOT / "hooks" / "hooks.json"
    if not hooks.exists():
        failures.append("missing hooks/hooks.json")

    skills = sorted((ROOT / "skills").glob("*/SKILL.md"))
    if len(skills) < 25:
        failures.append(f"too few skills: {len(skills)}")

    agents = sorted((ROOT / "agents").glob("*.md"))
    if len(agents) < 15:
        failures.append(f"too few agents: {len(agents)}")

    commands = sorted((ROOT / "commands").glob("*.md"))
    if len(commands) < 6:
        failures.append(f"too few commands: {len(commands)}")

    print(f"manifest:  {manifest.exists()}")
    print(f"mcp.json:  {mcp.exists()}")
    print(f"hooks:     {hooks.exists()}")
    print(f"skills:    {len(skills)}")
    print(f"agents:    {len(agents)}")
    print(f"commands:  {len(commands)}")

    if failures:
        print("\nFAILURES:")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("\nDiscovery layout OK.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
