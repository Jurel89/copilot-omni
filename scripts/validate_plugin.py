#!/usr/bin/env python3
"""Validate every skill, agent, and command has well-formed frontmatter."""
from __future__ import annotations

import sys
from pathlib import Path

REQUIRED_SKILL_FIELDS = {"name", "description"}
REQUIRED_AGENT_FIELDS = {"name", "description"}


def _parse_frontmatter(text: str) -> dict:
    if not text.startswith("---"):
        return {}
    end = text.find("\n---", 3)
    if end < 0:
        return {}
    block = text[3:end].strip()
    meta: dict = {}
    for line in block.splitlines():
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        meta[key.strip()] = value.strip().strip('"').strip("'")
    return meta


def main() -> int:
    root = Path(__file__).resolve().parent.parent
    failures = []

    skills = list((root / "skills").glob("*/SKILL.md"))
    for skill in skills:
        meta = _parse_frontmatter(skill.read_text(encoding="utf-8"))
        missing = REQUIRED_SKILL_FIELDS - meta.keys()
        if missing:
            failures.append(f"{skill}: missing frontmatter fields {missing}")

    agents = list((root / "agents").glob("*.md"))
    for agent in agents:
        meta = _parse_frontmatter(agent.read_text(encoding="utf-8"))
        missing = REQUIRED_AGENT_FIELDS - meta.keys()
        if missing:
            failures.append(f"{agent}: missing frontmatter fields {missing}")

    commands = list((root / "commands").glob("*.md"))
    for cmd in commands:
        meta = _parse_frontmatter(cmd.read_text(encoding="utf-8"))
        if "name" not in meta:
            failures.append(f"{cmd}: missing name frontmatter")

    print(f"skills:   {len(skills)}")
    print(f"agents:   {len(agents)}")
    print(f"commands: {len(commands)}")

    if len(skills) < 25:
        failures.append(f"insufficient skills: {len(skills)} < 25")
    if len(agents) < 15:
        failures.append(f"insufficient agents: {len(agents)} < 15")
    if len(commands) < 6:
        failures.append(f"insufficient commands: {len(commands)} < 6")

    if failures:
        print("\nFAILURES:")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("\nAll manifests valid.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
