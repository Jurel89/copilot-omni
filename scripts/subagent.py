#!/usr/bin/env python3
"""Subagent helper — invoke a specialized agent via `copilot -p ... --agent <name>`.

This is the Copilot-CLI equivalent of Claude Code's `Task(subagent_type=...)`.
Ported skills call this module to spawn an agent and capture its output.
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from typing import Optional


def run_agent(name: str, prompt: str,
              allow_all: bool = True,
              model: Optional[str] = None,
              timeout: int = 1800) -> int:
    copilot = shutil.which("copilot")
    if not copilot:
        print("error: `copilot` CLI not found on PATH", file=sys.stderr)
        return 2
    cmd = [copilot, "-p", prompt, "--agent", name]
    if allow_all:
        cmd.append("--allow-all")
    if model:
        cmd.extend(["--model", model])
    return subprocess.call(cmd, timeout=timeout)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a Copilot Omni subagent")
    parser.add_argument("name", help="Agent name (matches agents/<name>.md)")
    parser.add_argument("prompt", help="Task prompt to send the agent")
    parser.add_argument("--model", default=None)
    parser.add_argument("--no-allow-all", action="store_true")
    args = parser.parse_args()
    return run_agent(args.name, args.prompt,
                     allow_all=not args.no_allow_all,
                     model=args.model)


if __name__ == "__main__":
    sys.exit(main())
